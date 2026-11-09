"""Step ④: compliance checks.

L1 — deterministic rules from brand/brand_rules.yaml (+ catalog fact matching).
L2 — Gemini Flash reviewer for what regexes cannot see (fabrication, pushiness,
     ignored questions, tone, near-duplicate angles).
"""
from __future__ import annotations

import difflib
import re

from ..brand import Brand
from ..config import Settings
from ..llm import LLM, CallStats
from ..prompts import render
from ..schemas import SCENARIO_LABELS, Candidate, Flag, GenerateRequest, ReviewOutput
from .context import Context

# Emoji / pictograph ranges (enough for WeChat text; ZWJ & variation selectors folded in).
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿️‍\U0001F1E6-\U0001F1FF]"
)
_REPEATED_PUNCT = re.compile(r"([！!？?。，,~～、；;：:])\1+")
_LINK = re.compile(r"https?://|www\.|\.com\b|\.cn\b", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.、)）])\s+", re.M)
_PRICE = re.compile(
    r"(?:[¥￥]\s*(?P<a>\d[\d,]*(?:\.\d+)?)\s*(?P<au>万)?)|(?:(?P<b>\d[\d,]*(?:\.\d+)?)\s*(?P<bu>万元|万块|元|块|千元))"
)
_DATE_MD = re.compile(r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]")
_TIME = re.compile(r"(?<!\d)(?P<h>\d{1,2})[:：](?P<mi>\d{2})(?!\d)")
_DISCOUNT_WORD = re.compile(r"折扣|打折|优惠")
_NEGATION = re.compile(r"(没办法|不能|无法|没有|并不|不会|不参与|不做|不打|没|不|无)")
_QUESTION_FORM = re.compile(r"能不能|可不可以|是不是|有没有|会不会|行不行")
_DEMAND_VISIT = re.compile(
    r"(欢迎|请|邀请)您?.{0,6}(来店|到店|光临|过来看看|来看看)|(这周|本周|周末|明天|改天).{0,6}(来店|到店|过来看看)"
)
_AI_TONE = ["愿这份", "这份心意", "为您带来", "点亮您", "温暖您的", "每一个美好", "美好的回忆", "陪伴您度过"]


def char_len(text: str) -> int:
    return len(re.sub(r"\s", "", _EMOJI.sub("", text)))


def _mentioned_products(brand: Brand, text: str) -> set[str]:
    """Catalog products referred to by name. Variant products sharing a name collapse into one family."""
    hits: set[str] = set()
    seen_names: set[str] = set()
    for pid, p in brand.products.items():
        tokens = [p["name_cn"].split()[0], p["name_en"].split()[0] if p.get("name_en") else None]
        for t in tokens:
            if t and len(t) >= 2 and t in text and t not in seen_names:
                hits.add(pid)
                seen_names.add(t)
                break
    return hits


def _product_family(brand: Brand, pid: str) -> str:
    return brand.products[pid]["name_cn"].split()[0]


def _price_values(text: str) -> list[int]:
    vals = []
    for m in _PRICE.finditer(text):
        num = m.group("a") or m.group("b")
        unit = m.group("au") or m.group("bu") or ""
        v = float(num.replace(",", ""))
        if "万" in unit:
            v *= 10000
        elif unit == "千元":
            v *= 1000
        if v >= 100:  # ignore "3 元" style noise; prices here are ≥ ¥4,600
            vals.append(int(round(v)))
    return vals


def check_candidate(
    brand: Brand, req: GenerateRequest, ctx: Context, idx: int, text: str
) -> list[Flag]:
    rules = brand.rules
    flags: list[Flag] = []

    def add(level: str, code: str, detail: str) -> None:
        flags.append(Flag(candidate=idx, level=level, code=code, detail=detail))

    if not text.strip():
        add("hard", "empty", "候选为空")
        return flags

    # ---- length
    n = char_len(text)
    lim = rules["length"][req.scenario]
    if n > lim["max"]:
        add("hard", "too_long", f"{n} 字，超过上限 {lim['max']}")
    elif n < lim["min"]:
        add("soft", "too_short", f"{n} 字，低于建议 {lim['min']}")

    # ---- phrases & regex (hard)
    for ph in rules["hard_fail"]["phrases"]:
        if ph in text:
            add("hard", "forbidden_phrase", f"禁用词「{ph}」")
    for r in rules["hard_fail"]["regex"]:
        m = re.search(r["pattern"], text)
        if m:
            add("hard", r["name"], f"命中「{m.group(0)}」")

    # ---- discount words only allowed as refusal (all scenarios)
    for m in _DISCOUNT_WORD.finditer(text):
        before = _QUESTION_FORM.sub("", text[max(0, m.start() - 8) : m.start()])
        if not _NEGATION.search(before):
            add("hard", "discount_mention", f"「{text[max(0, m.start() - 6) : m.end()]}」不是明确拒绝语境")

    # ---- format
    fmt = rules["format"]
    ex = text.count("!") + text.count("！")
    if ex > fmt["max_exclamation"]:
        add("hard", "exclamation", f"感叹号 {ex} 个")
    if fmt.get("forbid_repeated_punctuation"):
        m = _REPEATED_PUNCT.search(text.replace("……", ""))
        if m:
            add("hard", "repeated_punct", f"连续标点「{m.group(0)}」")
    if fmt.get("forbid_links") and _LINK.search(text):
        add("hard", "link", "包含链接")
    for b in fmt.get("forbid_marketing_brackets", []):
        if b in text:
            add("hard", "marketing_format", f"营销格式符号「{b}」")
    if fmt.get("forbid_bullet_list") and _BULLET.search(text):
        add("hard", "bullet_list", "分点列表")

    # ---- emoji
    allowed = set(fmt["emoji"]["allowed"])
    emojis = [e for e in _EMOJI.findall(text) if e not in ("️", "‍")]
    bad = [e for e in emojis if e not in allowed]
    if bad:
        add("hard", "emoji_not_allowed", f"不允许的表情 {''.join(bad)}")
    if len(emojis) > ctx.emoji_max:
        add("hard", "emoji_count", f"表情 {len(emojis)} 个，本条上限 {ctx.emoji_max}")

    # ---- soft phrases, tail particles, AI tone
    for ph in rules["soft"]["phrases"]:
        if ph in text:
            add("soft", "cliche", f"套话「{ph}」")
    for tp in rules["soft"]["tail_particles"]:
        if tp in text:
            add("soft", "tail_particle", f"语气词「{tp}」")
    for ph in _AI_TONE:
        if ph in text:
            add("soft", "ai_tone", f"AI 腔「{ph}」")

    # ---- salutation & gender
    c = req.client
    surname = c.name[0] if c.name else ""
    names = [x for x in (c.name, c.preferred_name) if x]
    if names and not any(nm in text for nm in names) and (not surname or surname not in text):
        add("soft", "no_salutation", "没有称呼客户")
    if surname:
        if c.gender == "F" and re.search(f"{surname}先生", text):
            add("hard", "wrong_gender", f"女性客户被称为「{surname}先生」")
        if c.gender == "M" and re.search(f"{surname}(女士|小姐)", text):
            add("hard", "wrong_gender", "男性客户被称为女士/小姐")

    # ---- prices must come from the facts given
    allowed_prices = {int(brand.products[p].get("price", brand.products[p].get("price_from", 0))) for p in ctx.product_ids if p in brand.products}
    note_nums = {int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{2,}", req.product_note or "")}
    for v in _price_values(text):
        if v not in allowed_prices and v not in note_nums:
            add("hard", "unknown_price", f"价格 {v} 不在输入事实中")

    # ---- event facts
    if req.event_id and req.event_id in brand.events:
        ev = brand.events[req.event_id]
        ev_date = str(ev["date"])
        _, em, ed = ev_date.split("-")
        for m in _DATE_MD.finditer(text):
            if (int(m.group("m")), int(m.group("d"))) != (int(em), int(ed)):
                add("hard", "event_date", f"日期「{m.group(0)}」与活动资料 {ev_date} 不符")
        ev_time = str(ev.get("time", ""))
        ev_times = {(int(h), mi) for h, mi in re.findall(r"(\d{1,2})[:：](\d{2})", ev_time)}
        for m in _TIME.finditer(text):
            if (int(m.group("h")), m.group("mi")) not in ev_times:
                add("hard", "event_time", f"时间「{m.group(0)}」与活动资料「{ev_time}」不符")

    # ---- scenario constraints
    sc = rules.get("scenarios", {}).get(req.scenario, {})
    mentioned = _mentioned_products(brand, text)
    if sc.get("forbid_product_push"):
        owned_text = " ".join(p.product for p in c.purchases)
        owned_fams = {_product_family(brand, p) for p in ctx.product_ids if p in brand.products}
        for pid in mentioned:
            fam = _product_family(brand, pid)
            if fam not in owned_text and fam not in owned_fams:
                add("hard", "product_push", f"{SCENARIO_LABELS[req.scenario]}中提到未购产品「{fam}」")
    if "max_products_mentioned" in sc:
        fams = {_product_family(brand, p) for p in mentioned}
        if len(fams) > sc["max_products_mentioned"]:
            add("hard", "too_many_products", f"提到 {len(fams)} 个产品：{'、'.join(sorted(fams))}")
    if sc.get("forbid_demand_visit"):
        m = _DEMAND_VISIT.search(text)
        if m:
            add("hard", "demand_visit", f"唤醒消息要求到店「{m.group(0)}」")

    return flags


def check_set(brand: Brand, candidates: list[Candidate]) -> list[Flag]:
    flags: list[Flag] = []
    limit = brand.rules["diversity"]["max_pairwise_char_similarity"]
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i].text, candidates[j].text
            if not a or not b:
                continue
            r = difflib.SequenceMatcher(None, a, b).ratio()
            if a == b:
                flags.append(Flag(candidate=j, level="hard", code="duplicate", detail=f"与候选 {i + 1} 完全相同"))
            elif r > limit:
                flags.append(
                    Flag(candidate=j, level="soft", code="too_similar", detail=f"与候选 {i + 1} 相似度 {r:.2f}")
                )
    return flags


def max_pairwise_similarity(texts: list[str]) -> float:
    best = 0.0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            best = max(best, difflib.SequenceMatcher(None, texts[i], texts[j]).ratio())
    return best


def rules_digest(brand: Brand) -> str:
    return (
        "1. 不承诺/暗示折扣、优惠、内部价、赠品、返现，包括“帮您问问/申请”；\n"
        "2. 不贬低竞品、海外渠道或代购；\n"
        "3. 产品、价格、库存、活动信息只能来自输入事实；\n"
        "4. 不制造虚假稀缺或紧迫；\n"
        "5. 不提客户年龄、消费金额、等级、多久没来/没买；\n"
        "6. 生日/节日问候与售后关怀不推销新品；唤醒消息不要求到店；\n"
        "7. 客户的不满或问题必须先被回应；客户负面或拒绝时不推销；\n"
        "8. 口吻：像懂行可信赖的老朋友，温润、克制、具体、有分寸；不用“亲/宝/尊敬的”，不卖萌，不套话。"
    )


def llm_review(
    brand: Brand,
    req: GenerateRequest,
    ctx: Context,
    candidates: list[Candidate],
    llm: LLM,
    s: Settings,
    stats: CallStats,
) -> tuple[list[Flag], ReviewOutput]:
    system = render(
        s.prompt_version,
        "review_system",
        brand_name=f"{brand.rules['brand']['name_en']} {brand.rules['brand']['name_cn']}",
        rules_digest=rules_digest(brand),
    )
    prompt = render(
        s.prompt_version,
        "review_user",
        scenario_label=SCENARIO_LABELS[req.scenario],
        client=ctx.client_text,
        dialog=ctx.dialog_text,
        open_questions="；".join(ctx.open_questions) or "无",
        facts=ctx.facts_text,
        candidates="\n".join(f"[候选 {i}] 角度：{c.angle}\n{c.text}\n" for i, c in enumerate(candidates)),
    )
    out = llm.generate_json(
        task="review", model=s.fast_model, system=system, prompt=prompt, schema=ReviewOutput, stats=stats
    )
    flags: list[Flag] = []
    for r in out.candidates:
        if r.index < 0 or r.index >= len(candidates) or r.passed:
            continue
        issues = []
        if r.fabricated_facts:
            issues.append("捏造：" + "；".join(r.fabricated_facts))
        if r.pushy_or_salesy:
            issues.append("推销过度")
        if r.ignores_open_question:
            issues.append("未回应客户的问题/情绪")
        issues += r.off_brand_issues
        detail = "；".join(issues) or "审查未通过"
        if r.fix_instruction:
            detail += f"。建议：{r.fix_instruction}"
        flags.append(Flag(candidate=r.index, level="llm", code="llm_review", detail=detail))
    if out.too_similar:
        flags.append(Flag(candidate=None, level="soft", code="llm_too_similar", detail="审查认为三条角度雷同"))
    return flags, out
