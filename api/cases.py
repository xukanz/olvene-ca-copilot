"""Test-case YAML (eval/cases/cases.yaml) → GenerateRequest. Shared by the CLI and the eval job."""
from __future__ import annotations

from pathlib import Path

import yaml

from .config import ROOT
from .schemas import DialogTurn, GenerateRequest

CASES_FILE = ROOT / "eval" / "cases" / "cases.yaml"
SHOTS_DIR = ROOT / "eval" / "cases" / "screenshots"


def load_cases(path: Path | str = CASES_FILE) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def screenshot_paths(case_id: str) -> list[Path]:
    return sorted(SHOTS_DIR.glob(f"{case_id}_*.png"))


def case_to_request(case: dict, use_screenshots: bool = True) -> GenerateRequest:
    shots = screenshot_paths(case["id"]) if (use_screenshots and case.get("screenshot")) else []
    dialog = None
    if not shots:
        dialog = [DialogTurn(**t) for t in case.get("dialog") or []]
    client = dict(case["client"])
    client["purchases"] = [
        {"product": p["product"], "date": str(p.get("date")) if p.get("date") else None}
        for p in client.get("purchases") or []
    ]
    return GenerateRequest(
        scenario=case["scenario"],
        client=client,
        dialog=dialog,
        dialog_screenshots=[str(p) for p in shots],
        product_ids=case.get("product_ids") or [],
        event_id=case.get("event_id"),
        context={k: (str(v) if v is not None else None) for k, v in (case.get("context") or {}).items()},
    )
