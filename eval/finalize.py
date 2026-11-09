"""Assemble the submitted results: base run + re-run cases → final.jsonl, then export
section C (all 50 cases in the brief's columns) as xlsx and Markdown.

  python -m eval.finalize v2 v2.1_partial
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from api.cases import load_cases
from api.config import ROOT
from api.schemas import SCENARIO_LABELS

from .run_eval import RESULTS, _fmt_client, _fmt_product

OUT = ROOT / "submission"
SCENARIO_EN = {
    "birthday_festive": "Birthday and festive greetings",
    "product_recommendation": "Product recommendation",
    "post_purchase_care": "Post-purchase care",
    "reactivation": "Reactivation",
    "event_invitation": "Event invitation",
    "price_objection": "Price objection",
}


def _load(name: str) -> dict[str, dict]:
    return {json.loads(x)["case_id"]: json.loads(x) for x in (RESULTS / f"{name}.jsonl").read_text().splitlines() if x.strip()}


def _dialog(d: list[dict]) -> str:
    out = []
    for t in d:
        who = "CA" if t["speaker"] == "ca" else "客户"
        text = t["text"] + (f"（转文字：{t['transcript']}）" if t.get("transcript") else "")
        out.append(f"[{t['time']}] {who}：{text}" if t.get("time") else f"{who}：{text}")
    return "\n".join(out) or "（无对话记录）"


def main() -> None:
    base, *overrides = sys.argv[1:] or ["v2", "v2.1_partial"]
    final = _load(base)
    for o in overrides:
        final.update(_load(o))  # each record keeps its own "version"
    cases = load_cases()
    recs = [final[c["id"]] for c in cases]
    (RESULTS / "final.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n")

    rows = []
    for c, r in zip(cases, recs):
        cand = r["candidates"]
        rows.append(
            {
                "Case ID": c["id"],
                "Scenario": f"{SCENARIO_EN[c['scenario']]}（{SCENARIO_LABELS[c['scenario']]}）",
                "Client information": _fmt_client(c["client"]) + f"\n今天：{c['context']['today']}"
                + (f"；场合：{c['context']['occasion']}" if c["context"].get("occasion") else ""),
                "Conversation history": _dialog(c.get("dialog") or [])
                + (f"\n（工具输入为截图：{c['screenshot']['style']}）" if c.get("screenshot") else ""),
                "Product information": _fmt_product(c),
                "Output 1": f"【{cand[0]['angle']}】{cand[0]['text']}",
                "Output 2": f"【{cand[1]['angle']}】{cand[1]['text']}",
                "Output 3": f"【{cand[2]['angle']}】{cand[2]['text']}",
            }
        )
    df = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    with pd.ExcelWriter(OUT / "C_test_cases.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="C. 50 test cases", index=False)
        from openpyxl.styles import Alignment

        ws = xw.book["C. 50 test cases"]
        for col, w in zip("ABCDEFGH", [8, 18, 34, 46, 26, 44, 44, 44]):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "B2"

    md = ["# C. 50 test cases", "",
          "All outputs are unedited outputs of the final tool (v2). Each output starts with its angle 【…】. "
          "Same content as `C_test_cases.xlsx`.", "",
          "| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    for _, row in df.iterrows():
        md.append("| " + " | ".join(str(v).replace("|", "｜").replace("\n", "<br>") for v in row) + " |")
    (OUT / "C_test_cases.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"final.jsonl: {pd.Series([r['version'] for r in recs]).value_counts().to_dict()}")
    print(f"wrote {OUT / 'C_test_cases.xlsx'} and {OUT / 'C_test_cases.md'}")


if __name__ == "__main__":
    main()
