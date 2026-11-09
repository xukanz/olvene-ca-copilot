"""Human review vs. LLM judge (方案规划 §7.2: 15 sampled cases, ≥ 2 per scenario).

  python -m eval.human_review sample v1     # writes results/human_review_v1.xlsx to fill in by hand
  python -m eval.human_review agree v1      # after filling: agreement report vs. the judge
"""
from __future__ import annotations

import random
import sys

import pandas as pd

from api.schemas import SCENARIO_LABELS

from .report import load
from .run_eval import RESULTS

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
    rows = []
    for r in sorted(picked, key=lambda r: r["case_id"]):
        for i, c in enumerate(r["candidates"]):
            rows.append(
                {"case_id": r["case_id"], "idx": i + 1, "angle": c["angle"], "text": c["text"],
                 **{f"h_{d}": None for d in DIMS}, "h_red_line": None, "h_send_ready": None, "h_note": None}
            )
    out = RESULTS / f"human_review_{version}.xlsx"
    pd.DataFrame(rows).to_excel(out, index=False)
    print(f"wrote {out}: fill h_* columns (1–5; red_line/send_ready as 1/0)")


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
