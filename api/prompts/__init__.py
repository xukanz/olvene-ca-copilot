"""Versioned prompt templates: api/prompts/<version>/<name>.md, filled with string.Template."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=64)
def _load(version: str, name: str) -> Template:
    return Template((DIR / version / f"{name}.md").read_text(encoding="utf-8"))


def render(version: str, name: str, **values: object) -> str:
    return _load(version, name).substitute({k: "" if v is None else str(v) for k, v in values.items()})
