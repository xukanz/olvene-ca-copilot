"""Orchestrates ① parse → ② context → ③ generate → ④ check (→ targeted rewrite ≤ N)."""
from __future__ import annotations

import json
import logging
import time
import uuid

from ..brand import load_brand
from ..config import Settings, get_settings
from ..llm import LLM, CallStats
from ..schemas import CandidateOut, Checks, Flag, GenerateRequest, GenerateResponse
from .context import build_context
from .generate import generate, rewrite
from .guardrails import char_len, check_candidate, check_set, llm_review
from .parse_screenshot import analyze_dialog

log = logging.getLogger(__name__)


def _check_all(brand, req, ctx, cands, llm, s, stats) -> list[Flag]:
    flags: list[Flag] = []
    for i, c in enumerate(cands):
        flags += check_candidate(brand, req, ctx, i, c.text)
    flags += check_set(brand, cands)
    if s.llm_review:
        try:
            lf, _ = llm_review(brand, req, ctx, cands, llm, s, stats)
            flags += lf
        except Exception as e:  # reviewer failure must not block drafting
            log.warning("LLM review failed: %s", e)
            flags.append(Flag(level="info", code="review_unavailable", detail=str(e)[:200]))
    return flags


def _failing(flags: list[Flag]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for f in flags:
        if f.candidate is not None and f.level in ("hard", "llm"):
            out.setdefault(f.candidate, []).append(f"{f.code}: {f.detail}")
    return out


def run_pipeline(req: GenerateRequest, settings: Settings | None = None, llm: LLM | None = None) -> GenerateResponse:
    s = settings or get_settings()
    llm = llm or LLM(s)
    stats = CallStats()
    t0 = time.time()
    brand = load_brand(req.brand_id)

    analysis = analyze_dialog(req, llm, s, stats)
    ctx = build_context(brand, req, analysis, s.prompt_version)
    gen = generate(ctx, llm, s, stats)
    cands = gen.candidates

    flags = _check_all(brand, req, ctx, cands, llm, s, stats)
    retries = 0
    rewritten: set[int] = set()
    while retries < s.max_rewrites:
        failing = _failing(flags)
        if not failing:
            break
        retries += 1
        for idx, problems in failing.items():
            others = [c for j, c in enumerate(cands) if j != idx]
            try:
                cands[idx] = rewrite(ctx, cands[idx], problems, others, llm, s, stats)
                rewritten.add(idx)
            except Exception as e:
                log.warning("rewrite %d failed: %s", idx, e)
        flags = _check_all(brand, req, ctx, cands, llm, s, stats)

    failing = _failing(flags)
    out_cands = [
        CandidateOut(**c.model_dump(), passed=i not in failing, char_count=char_len(c.text)) for i, c in enumerate(cands)
    ]
    info = [Flag(level="info", code="care_mode", detail=n) for n in ctx.notes]
    unseen = [t.text for t in analysis.dialog if t.speaker == "client" and (
        (t.type == "voice" and not t.transcript) or t.type == "image")]
    if unseen:
        info.append(Flag(level="info", code="unseen_media", detail=(
            f"客户发了工具无法读取的内容（{'、'.join(unseen)}）。请先查看；如果内容重要，"
            "用微信“转文字”后重新截图，或在对话表里补充文字，再重新生成。")))
    if analysis.parse_confidence != "high" and (req.dialog_screenshots and req.dialog is None):
        info.append(
            Flag(level="info", code="parse_confidence", detail=f"截图解析置信度 {analysis.parse_confidence}：{analysis.parse_notes}")
        )
    resp = GenerateResponse(
        request_id="req_" + uuid.uuid4().hex[:12],
        parsed_dialog=analysis.dialog,
        dialog_summary=analysis.summary,
        client_sentiment=analysis.client_sentiment,
        open_questions=analysis.open_questions,
        plan=gen.plan,
        candidates=out_cands,
        checks=Checks(passed=not failing, retries=retries, flags=info + flags),
        meta={
            "model": s.gen_model,
            "fast_model": s.fast_model,
            "llm_mode": s.llm_mode,
            "brand_version": brand.version,
            "prompt_version": s.prompt_version,
            "angles": ctx.angles,
            "rewritten": sorted(rewritten),
            "latency_ms": int((time.time() - t0) * 1000),
            "llm_calls": stats.calls,
        },
    )
    if s.log_dir:
        s.log_dir.mkdir(parents=True, exist_ok=True)
        # Privacy: log parsed text only, never the screenshots themselves.
        payload = {"request": req.model_dump(exclude={"dialog_screenshots"}), "response": resp.model_dump()}
        (s.log_dir / f"{resp.request_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    return resp
