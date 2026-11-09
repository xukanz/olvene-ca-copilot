"""Step ②: deterministic context assembly (no LLM, no retrieval)."""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from ..brand import Brand
from ..prompts import render
from ..schemas import CARE_ANGLES, SCENARIO_ANGLES, SCENARIO_LABELS, DialogAnalysis, GenerateRequest
from .parse_screenshot import format_dialog


@dataclass
class Context:
    system: str
    user: str
    angles: list[str]
    facts_text: str
    client_text: str
    dialog_text: str
    open_questions: list[str]
    product_ids: list[str]  # products whose facts are allowed (requested + matched from purchases)
    emoji_max: int
    care_mode: bool
    notes: list[str] = field(default_factory=list)


def client_no_emoji(req: GenerateRequest) -> bool:
    style = req.client.comm_style or ""
    return req.client.no_emoji or any(k in style for k in ("不用表情", "不要表情", "不发表情", "无表情"))


def emoji_limit(brand: Brand, req: GenerateRequest) -> int:
    if client_no_emoji(req):
        return 0
    per = brand.rules["format"]["emoji"]["max_per_message"]
    return int(per.get(req.scenario, per.get("default", 0)))


def render_client(req: GenerateRequest) -> str:
    c = req.client
    lines = [f"称呼：{c.name}"]
    if c.preferred_name:
        lines.append(f"称呼偏好：{c.preferred_name}（可以这样称呼）")
    if c.gender:
        lines.append(f"性别：{'女' if c.gender == 'F' else '男'}")
    for label, val in [
        ("城市", c.city),
        ("关系阶段", c.relationship),
        ("偏好", "、".join(c.preferences) if c.preferences else None),
        ("重要日期", "、".join(c.important_dates) if c.important_dates else None),
        ("CA 笔记", c.notes),
        ("沟通偏好", c.comm_style),
        ("最近一次互动", c.last_interaction),
    ]:
        if val:
            lines.append(f"{label}：{val}")
    if c.purchases:
        lines.append("购买过：" + "；".join(f"{p.product}（{p.date}）" if p.date else p.product for p in c.purchases))
    if c.no_emoji:
        lines.append("不使用表情")
    return "\n".join(lines)


def _matched_purchase_products(brand: Brand, req: GenerateRequest) -> list[str]:
    hits = []
    for pid, names in brand.product_names().items():
        for p in req.client.purchases:
            if any(n and n in p.product for n in names):
                # 沙漏包 vs 沙漏包迷你: prefer the variant-specific entry when it is named.
                variant = brand.products[pid].get("variant")
                if variant and brand.products[pid]["name_cn"] == "沙漏包":
                    if ("迷你" in p.product or "Mini" in p.product) != (variant == "迷你款"):
                        continue
                hits.append(pid)
                break
    return hits


def render_facts(brand: Brand, req: GenerateRequest, product_ids: list[str]) -> str:
    cat = brand.catalog
    blocks: list[str] = []
    for pid in product_ids:
        p = brand.products.get(pid)
        if not p:
            continue
        tag = "本次相关产品" if pid in req.product_ids else "客户已购产品（仅用于保养/使用建议）"
        blocks.append(f"[{tag}]\n" + yaml.safe_dump(p, allow_unicode=True, sort_keys=False).strip())
    if req.product_note:
        blocks.append("[CA 补充的商品事实]\n" + req.product_note)
    if req.event_id:
        e = dict(brand.events.get(req.event_id) or {})
        if e:
            bids = e["boutique"] if isinstance(e["boutique"], list) else [e["boutique"]]
            e["boutique"] = "、".join(brand.boutiques.get(b, {}).get("name", b) for b in bids)
            blocks.append("[活动资料]\n" + yaml.safe_dump(e, allow_unicode=True, sort_keys=False).strip())
    blocks.append("[CA 可以提供的服务]\n" + "\n".join(f"- {x}" for x in cat.get("services", [])))
    blocks.append("[价格政策]\n" + "\n".join(f"- {x}" for x in cat.get("price_policy", [])))
    blocks.append("[门店]\n" + "、".join(b["name"] for b in cat.get("boutiques", [])))
    return "\n\n".join(blocks)


def build_context(brand: Brand, req: GenerateRequest, analysis: DialogAnalysis, prompt_version: str) -> Context:
    rules = brand.rules
    length = rules["length"][req.scenario]
    emax = emoji_limit(brand, req)
    allowed = " ".join(rules["format"]["emoji"]["allowed"])
    emoji_rule = "本条不使用任何表情" if emax == 0 else f"最多 {emax} 个，只能从 {allowed} 中选"
    if client_no_emoji(req):
        emoji_rule += "（客户偏好不用表情）"

    system = render(
        prompt_version,
        "generate_system",
        brand_name=f"{rules['brand']['name_en']} {rules['brand']['name_cn']}",
        brand_guide=brand.guide_md,
        length_rule=f"{length['min']}–{length['max']} 字",
        emoji_rule=emoji_rule,
        hard_phrases="、".join(rules["hard_fail"]["phrases"]),
        soft_phrases="、".join(rules["soft"]["phrases"]),
    )

    care_mode = analysis.client_sentiment == "negative" or analysis.client_declined
    notes: list[str] = []
    if care_mode:
        angles = CARE_ANGLES
        special = (
            "⚠️ 客户最近情绪负面或已明确拒绝：三条都不得推销或推进成交，先回应情绪/问题，"
            "再给出关怀或适当留白。场景目标让位于关系。"
        )
        notes.append("客户情绪负面或已拒绝，已切换为关怀/留白角度")
    else:
        angles = SCENARIO_ANGLES[req.scenario]
        special = ""
    if analysis.open_questions:
        special += "\n客户有尚未被回应的问题或情绪，每条候选都必须先回应它们（不知道答案时，坦诚说会去确认，不要编造）。"

    product_ids = list(dict.fromkeys(req.product_ids + _matched_purchase_products(brand, req)))
    facts = render_facts(brand, req, product_ids)
    client_text = render_client(req)
    dialog_text = format_dialog(analysis.dialog)

    fests = brand.festivals_near(req.context.today)
    cal_lines = []
    for f in fests:
        line = f"{f['name']} {f['date']}（距今天 {f['days_from_today']} 天）"
        if f.get("greet") is False:
            line += "，不发问候"
        if f.get("note"):
            line += f"，{f['note']}"
        cal_lines.append(line)

    occ = f"；场合：{req.context.occasion}" if req.context.occasion else ""
    user = render(
        prompt_version,
        "generate_user",
        scenario_label=SCENARIO_LABELS[req.scenario],
        scenario=req.scenario,
        today=req.context.today,
        occasion_line=occ,
        ca_name=req.context.ca_name or "（未提供）",
        angles="\n".join(f"候选{i + 1}：{a}" for i, a in enumerate(angles)),
        special_instruction=special.strip(),
        client=client_text,
        dialog_summary=analysis.summary or "无",
        client_sentiment=analysis.client_sentiment,
        open_questions="；".join(analysis.open_questions) or "无",
        dialog=dialog_text,
        facts=facts,
        calendar="\n".join(cal_lines) or "近期无节日",
        extra=f"CA 补充说明：{req.context.extra}" if req.context.extra else "",
    )
    return Context(
        system=system,
        user=user,
        angles=angles,
        facts_text=facts,
        client_text=client_text,
        dialog_text=dialog_text,
        open_questions=analysis.open_questions,
        product_ids=product_ids,
        emoji_max=emax,
        care_mode=care_mode,
        notes=notes,
    )
