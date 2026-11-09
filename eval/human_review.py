"""Human review vs. LLM judge (方案规划 §7.2: 15 sampled cases, ≥ 2 per scenario).

  python -m eval.human_review sample v1     # writes results/human_review_v1.xlsx to fill in by hand
  python -m eval.human_review agree v1      # after filling: agreement report vs. the judge
"""
from __future__ import annotations

import random
import sys

import pandas as pd

from api.schemas import SCENARIO_LABELS

from api.cases import load_cases

from .report import load
from .run_eval import RESULTS, _fmt_client, _fmt_dialog, _fmt_product

DIMS = ["personalisation", "on_brand", "timing", "naturalness", "cta"]


def sample(version: str, n: int = 15, seed: int = 7) -> None:
    recs = load(version)
    rng = random.Random(seed)
    picked = []
    for sc in SCENARIO_LABELS:
        pool = [r for r in recs if r["scenario"] == sc and not r.get("error")]
        picked += rng.sample(pool, min(2, len(pool)))
    rest = [r for r in recs if r not in picked and not r.get("error")]
    picked += rng.sample(rest, max(0, n - len(picked)))
    cases = {c["id"]: c for c in load_cases()}
    rows = []
    for r in sorted(picked, key=lambda r: r["case_id"]):
        c = cases[r["case_id"]]
        for i, cand in enumerate(r["candidates"]):
            rows.append(
                {
                    "case_id": r["case_id"],
                    "scenario": SCENARIO_LABELS[r["scenario"]],
                    # Context only on the first row of each case to keep the sheet readable.
                    "client": _fmt_client(c["client"]) if i == 0 else "",
                    "dialog": _fmt_dialog(c.get("dialog") or []) if i == 0 else "",
                    "product_event": _fmt_product(c) if i == 0 else "",
                    "today": str(c["context"].get("today")) if i == 0 else "",
                    "idx": i + 1,
                    "angle": cand["angle"],
                    "text": cand["text"],
                    **{f"h_{d}": None for d in DIMS},
                    "h_red_line": None,
                    "h_send_ready": None,
                    "h_note": None,
                }
            )
    out = RESULTS / f"human_review_{version}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        pd.DataFrame(rows).to_excel(xw, sheet_name="review", index=False)
        pd.DataFrame(GUIDE, columns=["列", "怎么填"]).to_excel(xw, sheet_name="说明", index=False)
        _style(xw.book)
    print(f"wrote {out}: fill h_* columns (1–5; red_line/send_ready as 1/0)")


GUIDE = [
    ("h_personalisation", "个性化 1–5。1 = 换个客户也能发；3 = 用了客户细节但很表面；5 = 细节具体且自然融入"),
    ("h_on_brand", "品牌口吻 1–5。1 = 销售腔/模板；3 = 礼貌但普通；5 = 温润、克制、具体，像欧薇恩"),
    ("h_timing", "时机与分寸 1–5。1 = 打扰或施压；3 = 可以接受；5 = 留有余地、分量恰当，完成了场景目标"),
    ("h_naturalness", "自然度 1–5。1 = 像脚本/AI；3 = 大体自然；5 = 像真实 CA 在微信上打的字"),
    ("h_cta", "行动号召 1–5。1 = 施压，或该有却没有；3 = 有但生硬；5 = 低压力、好回复"),
    ("h_red_line", "是否违反红线：1 = 违反，0 = 没有。红线：暗示折扣、贬低渠道、捏造（客户信息/对话/产品/活动，"
     "包括“您的语音我听了”这类声称知道未知内容）、虚假紧迫、提年龄或消费、无视投诉或情绪、生日/售后中推销、"
     "客户负面或拒绝时仍推销、不像微信消息"),
    ("h_send_ready", "如果你是 CA，会不会一个字不改直接发：1 = 会，0 = 不会。红线为 1 时这里必为 0"),
    ("h_note", "可选，一句话写主要问题，例如“捏造语音内容”“照抄示例句”。这些会成为缺陷清单"),
    ("打分建议", "先看第一行的 client / dialog / product_event / today，再读三条话术。"
     "普通合格就给 3，只有真正出色才给 5，分数拉开差距才有意义。不要看模型的打分，保持盲评。"),
    ("完成后", "保存文件，运行 python -m eval.human_review agree v1"),
]


def _style(wb) -> None:
    from openpyxl.styles import Alignment, PatternFill

    ws = wb["review"]
    widths = {"A": 7, "B": 9, "C": 26, "D": 30, "E": 16, "F": 10, "G": 4, "H": 9, "I": 45,
              "J": 9, "K": 9, "L": 9, "M": 9, "N": 9, "O": 9, "P": 9, "Q": 24}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    # Explicit opaque ARGB ("FF…"): openpyxl defaults the alpha to 00, which some viewers render as transparent.
    fill = PatternFill(fill_type="solid", start_color="FFFFE699", end_color="FFFFE699")
    head = PatternFill(fill_type="solid", start_color="FFFFC000", end_color="FFFFC000")
    for row in ws.iter_rows(min_row=1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if cell.column >= 10:
                cell.fill = head if cell.row == 1 else fill  # the cells to fill in
    # Freeze only the header row: freezing the wide context columns pushed the score columns off-screen.
    ws.freeze_panes = "A2"
    g = wb["说明"]
    g.column_dimensions["A"].width = 18
    g.column_dimensions["B"].width = 100
    for row in g.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def agree(version: str) -> None:
    hum = pd.read_excel(RESULTS / f"human_review_{version}.xlsx")
    recs = {r["case_id"]: r for r in load(version)}
    rows = []
    for _, h in hum.iterrows():
        sc = (recs[h["case_id"]].get("scores") or [None] * 3)[int(h["idx"]) - 1]
        if sc is None or pd.isna(h["h_send_ready"]):
            continue
        row = {"case_id": h["case_id"], "idx": h["idx"]}
        for d in DIMS:
            row[f"diff_{d}"] = abs(sc[d] - h[f"h_{d}"])
        row["send_ready_match"] = bool(sc["send_ready"]) == bool(h["h_send_ready"])
        row["red_line_match"] = bool(sc["red_line"]) == bool(h["h_red_line"])
        rows.append(row)
    df = pd.DataFrame(rows)
    print(f"messages compared: {len(df)}")
    for d in DIMS:
        within1 = (df[f"diff_{d}"] <= 1).mean()
        print(f"  {d:16s} MAE {df[f'diff_{d}'].mean():.2f}  within ±1: {within1:.0%}")
    print(f"  send_ready agreement {df['send_ready_match'].mean():.0%}")
    print(f"  red_line agreement   {df['red_line_match'].mean():.0%}")
    df.to_csv(RESULTS / f"human_agreement_{version}.csv", index=False)


if __name__ == "__main__":
    {"sample": sample, "agree": agree}[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else "v1")
