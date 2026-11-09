"""huashu-api: FastAPI entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .brand import load_brand
from .config import get_settings
from .llm import LLM, CallStats
from .pipeline.parse_screenshot import analyze_dialog
from .pipeline.run import run_pipeline
from .schemas import SCENARIO_ANGLES, SCENARIO_LABELS, DialogAnalysis, GenerateRequest, GenerateResponse

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Olvène CA Copilot API", version="1.0")


@app.get("/health")
@app.get("/healthz")  # local only: Cloud Run reserves paths ending in "z"
def healthz() -> dict:
    s = get_settings()
    return {"ok": True, "llm_mode": s.llm_mode, "prompt_version": s.prompt_version}


@app.get("/v1/meta")
def meta(brand_id: str = "olvene") -> dict:
    b = load_brand(brand_id)
    return {
        "brand_version": b.version,
        "scenarios": [{"id": k, "label": v, "angles": SCENARIO_ANGLES[k]} for k, v in SCENARIO_LABELS.items()],
        "products": [
            {"id": p["id"], "name": f"{p['name_cn']} {p.get('variant', '')} {p['name_en']}".replace("  ", " ")}
            for p in b.catalog["products"]
        ],
        "events": [{"id": e["id"], "name": f"{e['name']}（{e['date']}）"} for e in b.catalog["events"]],
    }


class ParseResponse(BaseModel):
    analysis: DialogAnalysis
    llm_calls: list[dict]


@app.post("/v1/parse", response_model=ParseResponse)
def parse(req: GenerateRequest) -> ParseResponse:
    """Step ① only, so the CA can review/correct the parsed dialog before generating."""
    s = get_settings()
    stats = CallStats()
    try:
        analysis = analyze_dialog(req, LLM(s), s, stats)
    except Exception as e:
        raise HTTPException(502, f"parse failed: {e}") from e
    return ParseResponse(analysis=analysis, llm_calls=stats.calls)


@app.post("/v1/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        return run_pipeline(req)
    except Exception as e:
        logging.exception("generate failed")
        raise HTTPException(502, f"generation failed: {e}") from e
