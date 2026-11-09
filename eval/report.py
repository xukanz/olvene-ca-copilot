"""Summarise one or more eval runs into Markdown tables + charts (SUBMISSION §D).

  python -m eval.report v1            # single version
  python -m eval.report v1 v2         # before / after comparison

Writes eval/results/report_<versions>.md and chart PNGs next to it.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from api.schemas import SCENARIO_LABELS  # noqa: E402

from .run_eval import RESULTS  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1-3, fixed order
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DIMS = ["personalisation", "on_brand", "timing", "naturalness", "cta"]
SC_SHORT = {k: f"S{i + 1}" for i, k in enumerate(SCENARIO_LABELS)}


def _cjk_font() -> None:
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/mnt/c/Windows/Fonts/msyh.ttc"):
        if Path(p).exists():
            font_manager.fontManager.addfont(p)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=p).get_name()
            return


def load(version: str) -> list[dict]:
    path = RESULTS / f"{version}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 2) if xs else None


def summarize(recs: list[dict]) -> dict:
    ok = [r for r in recs if not r.get("error")]
    msgs = [(r, i) for r in ok for i in range(3)]
    hard = [r["hard_fail"][i] for r, i in msgs]
    grades = [r["grades"][i] for r, i in msgs]
    scores = [r["scores"][i] for r, i in msgs if r.get("scores") and r["scores"][i]]
    judged = [g for g in grades if g != "unjudged"]
    out = {
        "cases": len(recs),
        "errors": len(recs) - len(ok),
        "hard_fail_rate": round(sum(hard) / len(hard), 3) if hard else None,
        "cases_with_hard_fail": sum(any(r["hard_fail"]) for r in ok),
        "unacceptable_rate": round(grades.count("unacceptable") / len(judged), 3) if judged else None,
        "good_rate": round(grades.count("good") / len(judged), 3) if judged else None,
        "send_ready_rate": round(sum(s["send_ready"] for s in scores) / len(scores), 3) if scores else None,
        "mean_weighted": _mean([s["weighted"] for s in scores]),
        "mean_diversity": _mean([r.get("diversity") for r in ok]),
        "mean_max_similarity": _mean([r.get("max_similarity") for r in ok]),
        "median_latency_ms": int(st.median([r["latency_ms"] for r in ok])) if ok else None,
        "mean_rewrites": _mean([r.get("retries", 0) for r in ok]),
        "parse_recall": _mean([r.get("parse_recall") for r in ok if r.get("input_mode") == "screenshot"]),
    }
    for d in DIMS:
        out[d] = _mean([s[d] for s in scores])
    return out


def by_scenario(recs: list[dict]) -> dict[str, dict]:
    return {sc: summarize([r for r in recs if r["scenario"] == sc]) for sc in SCENARIO_LABELS}


def _pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _num(x):
    return "—" if x is None else f"{x}"


def chart_scenarios(versions: list[str], per: dict[str, dict], path: Path) -> None:
    _cjk_font()
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    n = len(versions)
    width = 0.8 / n
    xs = range(len(SCENARIO_LABELS))
    for k, v in enumerate(versions):
        vals = [per[v][sc]["mean_weighted"] or 0 for sc in SCENARIO_LABELS]
        pos = [x - 0.4 + width * (k + 0.5) for x in xs]
        bars = ax.bar(pos, vals, width - 0.03, color=SERIES[k], label=v, zorder=2)
        for b, val in zip(bars, vals):
            if val:
                ax.text(b.get_x() + b.get_width() / 2, val + 0.05, f"{val:.2f}", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(list(xs), [f"{SC_SHORT[s]} {SCENARIO_LABELS[s]}" for s in SCENARIO_LABELS], fontsize=8, color=INK)
    ax.set_ylim(1, 5.3)
    ax.set_ylabel("加权平均分 (1–5)", fontsize=8, color=INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", labelsize=7, colors=INK2, length=0)
    if n > 1:
        ax.legend(frameon=False, fontsize=8, loc="upper left", ncols=n)
    ax.set_title("各场景 LLM judge 加权平均分", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    versions = sys.argv[1:] or ["v1"]
    data = {v: load(v) for v in versions}
    summ = {v: summarize(data[v]) for v in versions}
    per = {v: by_scenario(data[v]) for v in versions}
    tag = "_".join(versions)
    chart = RESULTS / f"report_{tag}_scenarios.png"
    chart_scenarios(versions, per, chart)

    L = [f"# Evaluation report · {' vs '.join(versions)}\n", "## D1. Summary\n"]
    L.append("| Metric | " + " | ".join(versions) + " |")
    L.append("|---|" + "---|" * len(versions))
    rows = [
        ("Cases (errors)", lambda s: f"{s['cases']} ({s['errors']})"),
        ("Hard-fail rate (messages, L1 after rewrites)", lambda s: _pct(s["hard_fail_rate"])),
        ("Cases with ≥ 1 hard fail", lambda s: _num(s["cases_with_hard_fail"])),
        ("Unacceptable rate (L1 or judge red line)", lambda s: _pct(s["unacceptable_rate"])),
        ("Good rate", lambda s: _pct(s["good_rate"])),
        ("Send-ready rate (judge)", lambda s: _pct(s["send_ready_rate"])),
        ("Mean weighted score", lambda s: _num(s["mean_weighted"])),
        ("Mean diversity (set, 1–5)", lambda s: _num(s["mean_diversity"])),
        ("Mean max pairwise similarity", lambda s: _num(s["mean_max_similarity"])),
        ("Screenshot parse recall", lambda s: _pct(s["parse_recall"])),
        ("Mean rewrites per case", lambda s: _num(s["mean_rewrites"])),
        ("Median latency per case (ms)", lambda s: _num(s["median_latency_ms"])),
    ]
    for label, f in rows:
        L.append(f"| {label} | " + " | ".join(f(summ[v]) for v in versions) + " |")

    for v in versions:
        L.append(f"\n## D2. By scenario · {v}\n")
        L.append("| Scenario | Hard-fail | Unacceptable | Good | " + " | ".join(DIMS) + " | Diversity | Weighted |")
        L.append("|---|" + "---|" * (len(DIMS) + 5))
        for sc, s in per[v].items():
            L.append(
                f"| {SC_SHORT[sc]} {SCENARIO_LABELS[sc]} | {_pct(s['hard_fail_rate'])} | {_pct(s['unacceptable_rate'])} | "
                f"{_pct(s['good_rate'])} | " + " | ".join(_num(s[d]) for d in DIMS)
                + f" | {_num(s['mean_diversity'])} | {_num(s['mean_weighted'])} |"
            )
    L.append(f"\n![scenario scores]({chart.name})\n")

    last = versions[-1]
    L.append(f"## Hard-fail and red-line list · {last}\n")
    for r in data[last]:
        for i in range(3):
            fl = [f"{f['code']}（{f['detail']}）" for f in r.get("flags", []) if f["level"] == "hard" and f["candidate"] == i]
            sc = (r.get("scores") or [None] * 3)[i]
            red = sc["red_line_reasons"] if sc and sc["red_line"] else []
            if fl or red:
                L.append(f"- **{r['case_id']} #{i + 1}** {'; '.join(fl + red)}  \n  > {r['candidates'][i]['text']}")

    L.append(f"\n## Lowest-scoring 10 messages · {last}\n")
    flat = [
        (r["scores"][i]["weighted"], r, i)
        for r in data[last]
        if r.get("scores")
        for i in range(3)
        if r["scores"][i]
    ]
    for w, r, i in sorted(flat, key=lambda x: x[0])[:10]:
        L.append(f"- **{r['case_id']} #{i + 1}** ({w}) {r['scores'][i]['comment']}  \n  > {r['candidates'][i]['text']}")

    out = RESULTS / f"report_{tag}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out} and {chart}")


if __name__ == "__main__":
    main()
