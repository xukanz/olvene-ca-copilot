"""Step ③: one call → three candidates with forced distinct angles (Gemini Pro)."""
from __future__ import annotations

from ..config import Settings
from ..llm import LLM, CallStats
from ..prompts import render
from ..schemas import Candidate, GenerationOutput, RewriteOutput
from .context import Context


def generate(ctx: Context, llm: LLM, s: Settings, stats: CallStats) -> GenerationOutput:
    out = llm.generate_json(
        task="generate",
        model=s.gen_model,
        system=ctx.system,
        prompt=ctx.user,
        schema=GenerationOutput,
        temperature=s.gen_temperature,
        stats=stats,
    )
    # Enforce exactly three, in angle order.
    cands = out.candidates[:3]
    while len(cands) < 3:
        cands.append(Candidate(angle=ctx.angles[len(cands)], text="", rationale="模型未返回该候选"))
    for i, c in enumerate(cands):
        if not c.angle:
            c.angle = ctx.angles[i]
        c.text = c.text.strip()
    out.candidates = cands
    return out


def rewrite(
    ctx: Context,
    cand: Candidate,
    problems: list[str],
    others: list[Candidate],
    llm: LLM,
    s: Settings,
    stats: CallStats,
) -> Candidate:
    prompt = render(
        s.prompt_version,
        "rewrite",
        angle=cand.angle,
        text=cand.text,
        problems="\n".join(f"- {p}" for p in problems),
        others="\n".join(f"- {o.text}" for o in others),
        task=ctx.user,
    )
    out = llm.generate_json(
        task="rewrite",
        model=s.gen_model,
        system=ctx.system,
        prompt=prompt,
        schema=RewriteOutput,
        temperature=max(0.4, s.gen_temperature - 0.2),
        stats=stats,
    )
    return Candidate(angle=cand.angle, text=out.text.strip(), rationale=out.rationale)
