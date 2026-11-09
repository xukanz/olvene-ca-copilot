"""Step ①: screenshots / text → structured dialog + analysis (Gemini Flash, multimodal)."""
from __future__ import annotations

import re

from ..config import Settings
from ..llm import LLM, CallStats, load_image
from ..prompts import render
from ..schemas import DialogAnalysis, DialogTurn, GenerateRequest

_SPEAKER = re.compile(r"^\s*(?:\[?(?P<time>[\d\-/: ]{4,16})\]?\s*)?(?P<who>[^:：]{1,12})[:：]\s*(?P<text>.+)$")
_CA_NAMES = {"ca", "我", "顾问", "CA"}


def format_dialog(turns: list[DialogTurn]) -> str:
    if not turns:
        return "（无对话记录）"
    lines = []
    for t in turns:
        who = {"ca": "CA", "client": "客户", "other": "其他人", "system": "系统"}[t.speaker]
        ts = f"[{t.time}] " if t.time else ""
        lines.append(f"{ts}{who}：{t.text}")
    return "\n".join(lines)


def analyze_dialog(req: GenerateRequest, llm: LLM, s: Settings, stats: CallStats) -> DialogAnalysis:
    system = render(s.prompt_version, "parse_system")

    if req.dialog is not None:
        if not req.dialog:
            return DialogAnalysis(summary="无对话记录。", client_sentiment="unknown")
        prompt = "以下是已经整理好的对话（无需重新识别，dialog 原样返回），请完成分析：\n" + format_dialog(req.dialog)
        out = llm.generate_json(
            task="analyze", model=s.fast_model, system=system, prompt=prompt, schema=DialogAnalysis, stats=stats
        )
        out.dialog = req.dialog  # trust the caller's (possibly CA-corrected) turns
        out.parse_confidence = "high"
        return out

    if req.dialog_text and req.dialog_text.strip():
        prompt = "以下是纯文本聊天记录，请整理并分析：\n" + req.dialog_text.strip()
        out = llm.generate_json(
            task="analyze", model=s.fast_model, system=system, prompt=prompt, schema=DialogAnalysis, stats=stats
        )
        if not out.dialog:  # mock mode or model returned nothing: deterministic fallback
            out.dialog = parse_text_dialog(req.dialog_text)
        return out

    if req.dialog_screenshots:
        images = [load_image(r) for r in req.dialog_screenshots]
        prompt = (
            f"以下是 {len(images)} 张微信截图，按顺序排列。客户称呼：{req.client.name}"
            + (f"（也可能显示为 {req.client.preferred_name}）" if req.client.preferred_name else "")
            + "。请整理并分析。"
        )
        return llm.generate_json(
            task="parse",
            model=s.fast_model,
            system=system,
            prompt=prompt,
            schema=DialogAnalysis,
            images=images,
            stats=stats,
        )

    return DialogAnalysis(summary="无对话记录。", client_sentiment="unknown")


def parse_text_dialog(text: str) -> list[DialogTurn]:
    """Best-effort `谁: 内容` line parser, used as a fallback."""
    turns: list[DialogTurn] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _SPEAKER.match(line)
        if not m:
            if turns:
                turns[-1].text += "\n" + line.strip()
            continue
        who = m.group("who").strip()
        speaker = "ca" if who in _CA_NAMES or who.lower() == "ca" else "client"
        turns.append(DialogTurn(speaker=speaker, time=(m.group("time") or "").strip() or None, text=m.group("text").strip()))
    return turns
