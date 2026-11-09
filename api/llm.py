"""Thin wrapper around google-genai (Vertex AI) with structured JSON output.

`LLM_MODE=mock` swaps in a deterministic fake so the whole pipeline, API, UI and
eval harness can run offline (tests, CI, demo without credentials).
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .config import Settings, get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class Image:
    data: bytes | None = None
    mime_type: str = "image/png"
    uri: str | None = None  # gs://...


def load_image(ref: str) -> Image:
    """Accepts gs:// URI, data URI, raw base64, or a local file path."""
    if ref.startswith("gs://"):
        mime = mimetypes.guess_type(ref)[0] or "image/png"
        return Image(uri=ref, mime_type=mime)
    if ref.startswith("data:"):
        header, b64 = ref.split(",", 1)
        mime = header[5:].split(";")[0] or "image/png"
        return Image(data=base64.b64decode(b64), mime_type=mime)
    p = Path(ref)
    if len(ref) < 1024 and p.exists():
        return Image(data=p.read_bytes(), mime_type=mimetypes.guess_type(p.name)[0] or "image/png")
    return Image(data=base64.b64decode(ref), mime_type="image/png")


@dataclass
class CallStats:
    calls: list[dict] = field(default_factory=list)

    def add(self, task: str, model: str, ms: int, usage: dict | None = None) -> None:
        self.calls.append({"task": task, "model": model, "ms": ms, **(usage or {})})


class LLM:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=self.s.project, location=self.s.location)
        return self._client

    def _thinking_for(self, model: str) -> str:
        """Per-model default thinking level; gen model uses GEN_THINKING, everything else FAST_THINKING."""
        return self.s.gen_thinking if model == self.s.gen_model else self.s.fast_thinking

    def generate_json(
        self,
        *,
        task: str,
        model: str,
        system: str,
        prompt: str,
        schema: type[T],
        temperature: float = 0.2,
        images: list[Image] | None = None,
        stats: CallStats | None = None,
        thinking_level: str | None = None,
    ) -> T:
        if self.s.llm_mode == "mock":
            t0 = time.time()
            out = schema.model_validate(_mock_response(task, prompt, schema))
            if stats:
                stats.add(task, "mock", int((time.time() - t0) * 1000))
            return out

        from google.genai import types

        parts: list[Any] = []
        for img in images or []:
            if img.uri:
                parts.append(types.Part.from_uri(file_uri=img.uri, mime_type=img.mime_type))
            else:
                parts.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))
        parts.append(types.Part.from_text(text=prompt))

        level = thinking_level if thinking_level is not None else self._thinking_for(model)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_level=level.upper()) if level else None,
        )
        last_err: Exception | None = None
        for attempt in range(3):
            t0 = time.time()
            try:
                resp = self.client.models.generate_content(
                    model=model, contents=[types.Content(role="user", parts=parts)], config=config
                )
                ms = int((time.time() - t0) * 1000)
                usage = None
                if um := resp.usage_metadata:
                    # Thinking tokens are billed as output but are not part of candidates_token_count.
                    usage = {
                        "in_tokens": um.prompt_token_count or 0,
                        "out_tokens": um.candidates_token_count or 0,
                        "thinking_tokens": um.thoughts_token_count or 0,
                        "total_tokens": um.total_token_count or 0,
                    }
                if stats:
                    stats.add(task, model, ms, usage)
                if isinstance(resp.parsed, schema):
                    return resp.parsed
                return schema.model_validate_json(_strip_fences(resp.text or ""))
            except Exception as e:  # noqa: BLE001 — retry transient + malformed JSON
                last_err = e
                log.warning("LLM %s attempt %d failed: %s", task, attempt + 1, e)
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM task {task} failed after retries: {last_err}")


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1) if m else text


# ---------------------------------------------------------------- mock backend


def _mock_response(task: str, prompt: str, schema: type[BaseModel]) -> dict:
    """Deterministic, rule-compliant canned outputs keyed by task."""
    name = _grab(prompt, r"称呼[:：]\s*(\S+)") or "您"
    if task == "parse":
        return {
            "dialog": [],
            "summary": "（mock）未解析截图。",
            "client_sentiment": "unknown",
            "open_questions": [],
            "parse_confidence": "low",
            "parse_notes": "mock 模式不读取图片",
        }
    if task == "analyze":
        return {"dialog": [], "summary": "（mock）对话摘要。", "client_sentiment": "neutral", "open_questions": []}
    if task == "generate":
        angles = re.findall(r"候选\d[:：]\s*(\S+)", prompt)[:3] or ["角度一", "角度二", "角度三"]
        texts = [
            f"{name}，最近好吗？天气转凉了，出门记得添件外套。之前聊到的事我一直记着，您方便时告诉我就好。",
            f"{name}，想起上次您说喜欢简单耐看的东西，这句话我一直记得。最近有什么新鲜事，也欢迎跟我聊聊。",
            f"{name}，不打扰您太久，只是想问候一声。这段时间如果有需要我帮忙的地方，随时找我。",
        ]
        return {
            "plan": {"stage": "mock", "must_address": [], "timing_note": "mock"},
            "candidates": [
                {"angle": a, "text": t, "rationale": "（mock）用于离线联调"} for a, t in zip(angles, texts)
            ],
        }
    if task == "rewrite":
        return {"text": f"{name}，这段时间还好吗？有任何需要随时找我，我都在。", "rationale": "（mock）改写"}
    if task == "review":
        n = len(re.findall(r"^\[候选 \d\]", prompt, re.M)) or 3
        return {
            "candidates": [
                {
                    "index": i,
                    "fabricated_facts": [],
                    "pushy_or_salesy": False,
                    "ignores_open_question": False,
                    "off_brand_issues": [],
                    "passed": True,
                    "fix_instruction": "",
                }
                for i in range(n)
            ],
            "too_similar": False,
        }
    # Generic: fill required fields with neutral defaults (used by eval judge in mock mode).
    out = _defaults_for(schema)
    for i, item in enumerate(out.get("candidates", []) if isinstance(out, dict) else []):
        if isinstance(item, dict) and "index" in item:
            item["index"] = i
    return out


def _defaults_for(schema: type[BaseModel]) -> dict:
    js = schema.model_json_schema()
    defs = js.get("$defs", {})

    def fill(node: dict) -> Any:
        if "$ref" in node:
            return fill(defs[node["$ref"].split("/")[-1]])
        if "anyOf" in node:
            return fill(node["anyOf"][0])
        t = node.get("type")
        if t == "object":
            return {k: fill(v) for k, v in node.get("properties", {}).items()}
        if t == "array":
            return [fill(node["items"]) for _ in range(node.get("minItems", 3) or 3)]
        if t == "integer":
            return max(node.get("minimum", 4), min(4, node.get("maximum", 4)))
        if t == "number":
            return 4.0
        if t == "boolean":
            return False
        if "enum" in node:
            return node["enum"][0]
        return "（mock）"

    return fill(js)


def _grab(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1).strip("，,。") if m else None


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
