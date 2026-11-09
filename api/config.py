"""Runtime configuration, all from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # "vertex" calls Gemini on Gemini Enterprise Agent Platform (formerly Vertex AI); "mock" returns canned outputs (offline tests, CI).
    llm_mode: str = field(default_factory=lambda: _env("LLM_MODE", "vertex"))
    project: str | None = field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT"))
    location: str = field(default_factory=lambda: _env("GOOGLE_CLOUD_LOCATION", "global"))
    gen_model: str = field(default_factory=lambda: _env("GEN_MODEL", "gemini-3.1-pro-preview"))
    fast_model: str = field(default_factory=lambda: _env("FAST_MODEL", "gemini-3-flash-preview"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "gemini-3-flash-preview"))
    # Gemini 3 thinking level per model: minimal | low | medium | high, or "" for the model default (high).
    # Flash does screenshot parsing / review / judging, where default thinking mostly adds latency.
    gen_thinking: str = field(default_factory=lambda: _env("GEN_THINKING", ""))
    fast_thinking: str = field(default_factory=lambda: _env("FAST_THINKING", "low"))
    gen_temperature: float = field(default_factory=lambda: float(_env("GEN_TEMPERATURE", "0.8")))
    max_rewrites: int = field(default_factory=lambda: int(_env("MAX_REWRITES", "2")))
    llm_review: bool = field(default_factory=lambda: _env("LLM_REVIEW", "1") == "1")
    prompt_version: str = field(default_factory=lambda: _env("PROMPT_VERSION", "v1"))
    brand_dir: Path = field(default_factory=lambda: Path(_env("BRAND_DIR", str(ROOT / "brand"))))
    log_dir: Path | None = field(
        default_factory=lambda: Path(os.environ["LOG_DIR"]) if os.environ.get("LOG_DIR") else None
    )


def get_settings() -> Settings:
    return Settings()
