"""Batch evaluation (Cloud Run Job entry point, also runs locally).

  python -m eval.run_eval --version v1                  # all 50 cases, screenshots where available
  python -m eval.run_eval --version v1 --only S6-02,S1-01
  python -m eval.run_eval --version v1 --text-dialog    # bypass screenshot parsing

Writes eval/results/<version>.jsonl (full records), <version>.csv and <version>.xlsx
(SUBMISSION §C columns + scores). RESULTS_DIR overrides the output directory.
"""
from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from api.brand import load_brand
from api.cases import case_to_request, load_cases
from api.config import ROOT, get_settings
from api.llm import CallStats
from api.pipeline.context import build_context, render_client
from api.pipeline.guardrails import max_pairwise_similarity
from api.pipeline.parse_screenshot import format_dialog
from api.pipeline.run import run_pipeline
from api.schemas import SCENARIO_LABELS, DialogAnalysis, DialogTurn

from .judge import JUDGE_VERSION, judge_case, weighted

# On Cloud Run Jobs, mount a GCS bucket as a volume and point RESULTS_DIR at it.
RESULTS = Path(os.environ.get("RESULTS_DIR", str(ROOT / "eval" / "results")))
log = logging.getLogger("eval")


def parse_recall(truth: list[dict], parsed: list[dict]) -> float | None:
    """Share of ground-truth ca/client turns recovered with the right speaker (fuzzy text match)."""
    gt = [t for t in truth if t["speaker"] in ("ca", "client") and t.get("type", "text") == "text"]
    if not gt:
        return None
    hit = 0
    for t in gt:
        for p in parsed:
            if p["speaker"] == t["speaker"] and difflib.SequenceMatcher(None, t["text"], p["text"]).ratio() >= 0.8:
                hit += 1
                break
    return round(hit / len(gt), 3)


def grade(hard: bool, sc: dict | None) -> str:
    if hard or (sc and sc["red_line"]):
        return "unacceptable"
    if sc is None:
        return "unjudged"
    if sc["send_ready"] and min(sc["personalisation"], sc["on_brand"], sc["naturalness"]) >= 4:
        return "good"
    return "acceptable"


def run_case(case: dict, version: str, use_screens: bool, do_judge: bool) -> dict:
    s = get_settings()
    t0 = time.time()
    req = case_to_request(case, use_screenshots=use_screens)
    rec: dict = {"case_id": case["id"], "scenario": case["scenario"], "title": case.get("title"), "version": version}
    try:
        resp = run_pipeline(req, settings=s)
    except Exception as e:  # keep the batch going
        log.exception("case %s failed", case["id"])
        return {**rec, "error": str(e)}
    r = resp.model_dump()
    rec.update(
        {
            "input_mode": "screenshot" if req.dialog_screenshots else ("text" if case.get("dialog") else "none"),
            "screenshot_style": (case.get("screenshot") or {}).get("style"),
            "parsed_dialog": r["parsed_dialog"],
            "dialog_summary": r["dialog_summary"],
            "client_sentiment": r["client_sentiment"],
            "open_questions": r["open_questions"],
            "plan": r["plan"],
            "candidates": r["candidates"],
            "flags": r["checks"]["flags"],
            "retries": r["checks"]["retries"],
            "meta": r["meta"],
            "latency_ms": r["meta"]["latency_ms"],
            "max_similarity": round(max_pairwise_similarity([c["text"] for c in r["candidates"]]), 3),
        }
    )
    if req.dialog_screenshots:
        rec["parse_recall"] = parse_recall(case.get("dialog") or [], r["parsed_dialog"])

    hard_by_idx = {f["candidate"] for f in r["checks"]["flags"] if f["level"] == "hard" and f["candidate"] is not None}
    rec["hard_fail"] = [i in hard_by_idx for i in range(3)]

    rec["scores"] = None
    if do_judge:
        judge_record(case, rec)
    rec["grades"] = [grade(rec["hard_fail"][i], rec["scores"][i] if rec["scores"] else None) for i in range(3)]
    rec["wall_ms"] = int((time.time() - t0) * 1000)
    return rec


def judge_record(case: dict, rec: dict) -> dict:
    """Score rec["candidates"] in place. The judge always sees the ground-truth dialog, not the parsed one."""
    s = get_settings()
    brand = load_brand()
    req = case_to_request(case, use_screenshots=False)
    truth = DialogAnalysis(dialog=req.dialog or [])
    ctx = build_context(brand, req, truth, s.prompt_version)
    stats = CallStats()
    rec.pop("judge_error", None)
    try:
        j = judge_case(
            case, render_client(req), format_dialog(truth.dialog), ctx.facts_text, rec["candidates"], s, stats,
            dialog_state=ctx.state.text if ctx.state else "",
        )
        scores = [None, None, None]
        for cs in j.candidates:
            if 0 <= cs.index < 3:
                scores[cs.index] = {**cs.model_dump(), "weighted": weighted(cs)}
        rec["scores"] = scores
        rec["diversity"] = j.diversity
        rec["set_comment"] = j.set_comment
        rec["judge_calls"] = stats.calls
    except Exception as e:
        log.warning("judge failed for %s: %s", case["id"], e)
        rec["judge_error"] = str(e)
        rec["scores"] = None
    rec["judge_version"] = JUDGE_VERSION
    rec["judge_model"] = s.judge_model
    return rec


def rejudge(case: dict, rec: dict, version: str) -> dict:
    rec = {**rec, "version": version}
    judge_record(case, rec)
    rec["grades"] = [grade(rec["hard_fail"][i], rec["scores"][i] if rec["scores"] else None) for i in range(3)]
    return rec


def _fmt_client(c: dict) -> str:
    parts = [f"{c['name']}（{c.get('relationship', '')}，{c.get('city') or '城市未知'}）"]
    if c.get("preferred_name"):
        parts.append(f"称呼偏好 {c['preferred_name']}")
    if c.get("purchases"):
        parts.append("购买：" + "；".join(f"{p['product']} {p.get('date') or ''}".strip() for p in c["purchases"]))
    if c.get("preferences"):
        parts.append("偏好：" + "、".join(c["preferences"]))
    if c.get("important_dates"):
        parts.append("日期：" + "、".join(c["important_dates"]))
    if c.get("notes"):
        parts.append("笔记：" + c["notes"])
    if c.get("comm_style"):
        parts.append("沟通：" + c["comm_style"])
    return "\n".join(parts)


def _fmt_dialog(d: list[dict]) -> str:
    return "\n".join(f"{'CA' if t['speaker'] == 'ca' else '客户'}：{t['text']}" for t in d) or "（无）"


def _fmt_product(case: dict) -> str:
    b = load_brand()
    out = []
    for pid in case.get("product_ids") or []:
        p = b.products[pid]
        price = p.get("price") or p.get("price_from")
        out.append(f"{pid} {p['name_cn']} {p.get('variant', '')} {p['name_en']} ¥{price:,}".replace("  ", " "))
    if case.get("event_id"):
        e = b.events[case["event_id"]]
        out.append(f"{e['id']} {e['name']} {e['date']} {e['time']}")
    return "\n".join(out) or "—"


def to_table(records: list[dict], cases: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        c = cases[r["case_id"]]
        row = {
            "Case ID": r["case_id"],
            "Scenario": SCENARIO_LABELS[r["scenario"]],
            "Client information": _fmt_client(c["client"]),
            "Conversation history": _fmt_dialog(c.get("dialog") or []),
            "Product information": _fmt_product(c),
        }
        cands = r.get("candidates") or []
        for i in range(3):
            row[f"Output {i + 1}"] = f"【{cands[i]['angle']}】{cands[i]['text']}" if i < len(cands) else ""
        row["Version"] = r["version"]
        sc = r.get("scores") or [None] * 3
        for i in range(3):
            row[f"Grade {i + 1}"] = (r.get("grades") or ["error"] * 3)[i]
            row[f"Score {i + 1}"] = sc[i]["weighted"] if sc[i] else None
        row["Diversity"] = r.get("diversity")
        row["Hard flags"] = "; ".join(
            f"#{f['candidate'] + 1} {f['code']}" for f in r.get("flags", []) if f["level"] == "hard" and f["candidate"] is not None
        )
        row["Rewrites"] = r.get("retries")
        row["Input mode"] = r.get("input_mode")
        row["Parse recall"] = r.get("parse_recall")
        row["Latency ms"] = r.get("latency_ms")
        row["Error"] = r.get("error") or r.get("judge_error")
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=os.environ.get("EVAL_VERSION", get_settings().prompt_version))
    ap.add_argument("--only", default=os.environ.get("EVAL_ONLY", ""))
    ap.add_argument("--text-dialog", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--rejudge", metavar="FROM", help="re-score FROM.jsonl outputs with the current judge, no regeneration")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("EVAL_WORKERS", "4")))
    a = ap.parse_args()

    cases = load_cases()
    if a.only:
        ids = {x.strip() for x in a.only.split(",")}
        cases = [c for c in cases if c["id"] in ids]
    by_id = {c["id"]: c for c in load_cases()}
    RESULTS.mkdir(parents=True, exist_ok=True)

    records = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        if a.rejudge:
            prev = {json.loads(x)["case_id"]: json.loads(x) for x in (RESULTS / f"{a.rejudge}.jsonl").read_text().splitlines() if x.strip()}
            futs = {ex.submit(rejudge, c, prev[c["id"]], a.version): c["id"] for c in cases if c["id"] in prev}
        else:
            futs = {ex.submit(run_case, c, a.version, not a.text_dialog, not a.no_judge): c["id"] for c in cases}
        for f in as_completed(futs):
            rec = f.result()
            records.append(rec)
            log.info("%s done %s %s", rec["case_id"], rec.get("grades"), rec.get("error", ""))
    records.sort(key=lambda r: r["case_id"])

    suffix = "" if not a.only else "_partial"
    name = f"{a.version}{suffix}"
    # Not Path.with_suffix: version names like "v2.1" contain a dot and would be truncated to "v2".
    out = {ext: RESULTS / f"{name}.{ext}" for ext in ("jsonl", "csv", "xlsx")}
    out["jsonl"].write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
    df = to_table(records, by_id)
    df.to_csv(out["csv"], index=False, encoding="utf-8-sig")
    df.to_excel(out["xlsx"], index=False)
    print(f"wrote {RESULTS / name}.jsonl / .csv / .xlsx ({len(records)} cases)")


if __name__ == "__main__":
    main()
