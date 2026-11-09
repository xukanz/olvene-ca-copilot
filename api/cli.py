"""Local CLI (demo backup when the web app is unreachable).

  python -m api.cli request.json                 # a GenerateRequest as JSON or YAML
  python -m api.cli eval/cases/cases.yaml S6-02  # one case from the test set
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .cases import case_to_request
from .pipeline.run import run_pipeline
from .schemas import GenerateRequest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("case_id", nargs="?")
    ap.add_argument("--text-dialog", action="store_true", help="ignore screenshots, use the case's dialog text")
    ap.add_argument("--json", action="store_true", help="print the full JSON response")
    a = ap.parse_args()

    data = yaml.safe_load(Path(a.file).read_text(encoding="utf-8"))
    if isinstance(data, list):
        if not a.case_id:
            sys.exit("case_id required for a cases file")
        case = next((c for c in data if c["id"] == a.case_id), None)
        if case is None:
            sys.exit(f"case {a.case_id} not found")
        req = case_to_request(case, use_screenshots=not a.text_dialog)
    else:
        req = GenerateRequest.model_validate(data)

    resp = run_pipeline(req)
    if a.json:
        print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=1))
        return
    print(f"# {resp.request_id}  {resp.meta['prompt_version']} / {resp.meta['brand_version']}  {resp.meta['latency_ms']} ms")
    print(f"摘要：{resp.dialog_summary}  情绪：{resp.client_sentiment}")
    if resp.open_questions:
        print("未回应：" + "；".join(resp.open_questions))
    for i, c in enumerate(resp.candidates, 1):
        mark = "✓" if c.passed else "✗"
        print(f"\n[{i}] {mark} {c.angle}（{c.char_count} 字）\n{c.text}\n  — {c.rationale}")
    if resp.checks.flags:
        print("\nflags:")
        for f in resp.checks.flags:
            who = f"候选{f.candidate + 1}" if f.candidate is not None else "整体"
            print(f"  - [{f.level}] {who} {f.code}: {f.detail}")


if __name__ == "__main__":
    main()
