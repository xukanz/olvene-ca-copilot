"""Render fictional WeChat chat screenshots for test cases (submission/B_methodology.md §B2).

  python -m eval.render_wechat            # all cases with a `screenshot` block
  python -m eval.render_wechat S6-02      # selected cases

Styles: normal | blurry | cropped | group_chat | multi | emoji_heavy.
Fonts: set WECHAT_FONT / WECHAT_EMOJI_FONT, or rely on the search list below.
"""
from __future__ import annotations

import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from api.cases import SHOTS_DIR, load_cases

W = 750
PAD = 24
AVATAR = 72
BUBBLE_MAX = 470
FONT_SIZE = 30
BG = (237, 237, 237)
GREEN = (149, 236, 105)
WHITE = (255, 255, 255)
TEXT = (25, 25, 25)
GREY = (150, 150, 150)

FONT_CANDIDATES = [
    os.environ.get("WECHAT_FONT", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
EMOJI_CANDIDATES = [
    os.environ.get("WECHAT_EMOJI_FONT", ""),
    "/mnt/c/Windows/Fonts/seguiemj.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")


def _font(cands: list[str], size: int):
    for p in cands:
        if p and Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return None


FONT = _font(FONT_CANDIDATES, FONT_SIZE)
SMALL = _font(FONT_CANDIDATES, 22)
TITLE = _font(FONT_CANDIDATES, 32)
EMOJI = _font(EMOJI_CANDIDATES, FONT_SIZE)
TITLE_EMOJI = _font(EMOJI_CANDIDATES, 32)
if FONT is None:
    sys.exit("No CJK font found; set WECHAT_FONT to a .ttf/.ttc with Chinese glyphs")


def _char_font(ch: str):
    return EMOJI if (EMOJI and _EMOJI.match(ch)) else FONT


def _char_w(ch: str) -> int:
    f = _char_font(ch)
    return int(f.getlength(ch)) if ch not in "️‍" else 0


def _wrap(text: str, width: int) -> list[str]:
    lines, cur, cw = [], "", 0
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur, cw = "", 0
            continue
        w = _char_w(ch)
        # Line-start prohibition: closing punctuation stays on the current line, like WeChat.
        if cw + w > width and cur and ch not in "，。、；：？！）」』”’,.;:?!)":
            lines.append(cur)
            cur, cw = "", 0
        cur += ch
        cw += w
    lines.append(cur)
    return lines


def _draw_text(d: ImageDraw.ImageDraw, xy: tuple[int, int], line: str) -> None:
    x, y = xy
    for ch in line:
        f = _char_font(ch)
        if f is EMOJI:
            d.text((x, y + 2), ch, font=f, embedded_color=True)
        else:
            d.text((x, y), ch, font=f, fill=TEXT)
        x += _char_w(ch)


def _draw_title(d: ImageDraw.ImageDraw, title: str) -> None:
    def f(ch):
        return TITLE_EMOJI if (TITLE_EMOJI and _EMOJI.match(ch)) else TITLE

    total = sum(int(f(c).getlength(c)) for c in title)
    x = (W - total) // 2
    for ch in title:
        fo = f(ch)
        if fo is TITLE_EMOJI:
            d.text((x, 50), ch, font=fo, embedded_color=True, anchor="lm")
        else:
            d.text((x, 50), ch, font=fo, fill=TEXT, anchor="lm")
        x += int(fo.getlength(ch))


def _avatar(d: ImageDraw.ImageDraw, x: int, y: int, label: str, color: tuple) -> None:
    d.rounded_rectangle([x, y, x + AVATAR, y + AVATAR], radius=8, fill=color)
    d.text((x + AVATAR // 2, y + AVATAR // 2), label[:1], font=TITLE, fill=WHITE, anchor="mm")


def _time_label(t: str) -> str:
    try:
        dt = datetime.strptime(t.strip(), "%m-%d %H:%M")
        return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    except ValueError:
        return t


def _minutes(t: str | None) -> int | None:
    if not t:
        return None
    try:
        dt = datetime.strptime(t.strip(), "%m-%d %H:%M")
        return ((dt.month * 31 + dt.day) * 24 + dt.hour) * 60 + dt.minute
    except ValueError:
        return None


def render(turns: list[dict], title: str, group: bool = False, client_nick: str = "客户") -> Image.Image:
    rows: list[tuple[str, object]] = []
    last = None
    for t in turns:
        m = _minutes(t.get("time"))
        if t.get("time") and (last is None or m is None or m - last >= 5):
            rows.append(("time", _time_label(t["time"])))
        if m is not None:
            last = m
        rows.append(("msg", t))

    # measure
    heights = []
    for kind, val in rows:
        if kind == "time":
            heights.append(56)
            continue
        t = val
        typ = t.get("type", "text")
        if typ == "image":
            h = 260
        elif typ == "sticker":
            h = 150
        else:
            h = len(_wrap(t["text"], BUBBLE_MAX - 40)) * 42 + 30
        if typ == "voice" and t.get("transcript"):
            h += 12 + len(_wrap(t["transcript"], BUBBLE_MAX - 40)) * 42 + 24
        if group and t["speaker"] != "ca":
            h += 30
        heights.append(max(h, AVATAR) + 28)
    H = 110 + sum(heights) + 40
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # title bar
    d.rectangle([0, 0, W, 96], fill=(247, 247, 247))
    _draw_title(d, title)
    d.text((PAD, 50), "‹", font=TITLE, fill=TEXT, anchor="lm")
    d.text((W - PAD, 50), "···", font=TITLE, fill=TEXT, anchor="rm")
    d.line([0, 96, W, 96], fill=(220, 220, 220), width=1)

    y = 110
    for (kind, val), h in zip(rows, heights):
        if kind == "time":
            d.text((W // 2, y + 24), val, font=SMALL, fill=GREY, anchor="mm")
            y += h
            continue
        t = val
        mine = t["speaker"] == "ca"
        typ = t.get("type", "text")
        nick = t.get("nick") or (client_nick if t["speaker"] == "client" else "")
        ax = W - PAD - AVATAR if mine else PAD
        color = (90, 130, 170) if mine else ((200, 140, 110) if t["speaker"] == "client" else (130, 160, 120))
        _avatar(d, ax, y, "我" if mine else (nick or "客"), color)
        by = y
        if group and not mine:
            d.text((ax + AVATAR + 20, y), nick, font=SMALL, fill=GREY)
            by += 30
        if typ == "image":
            bw, bh = 200, 240
            bx = ax - 20 - bw if mine else ax + AVATAR + 20
            d.rectangle([bx, by, bx + bw, by + bh], fill=(200, 205, 210))
            d.text((bx + bw // 2, by + bh // 2), "图片", font=SMALL, fill=(110, 110, 110), anchor="mm")
        elif typ == "sticker":
            bx = ax - 20 - 120 if mine else ax + AVATAR + 20
            d.ellipse([bx, by, bx + 120, by + 120], fill=(255, 205, 80))
            d.arc([bx + 30, by + 50, bx + 90, by + 95], 20, 160, fill=(120, 80, 20), width=5)
        else:
            text = t["text"]
            if typ == "voice":
                secs = re.search(r"(\d+)", text)
                text = f"{secs.group(1) if secs else 5}″  ))))" if mine else f"((((  {secs.group(1) if secs else 5}″"
            lines = _wrap(text, BUBBLE_MAX - 40)
            tw = max(sum(_char_w(c) for c in ln) for ln in lines)
            bw, bh = tw + 40, len(lines) * 42 + 26
            bx = ax - 20 - bw if mine else ax + AVATAR + 20
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=10, fill=GREEN if mine else WHITE)
            tip = [(bx + bw, by + 26), (bx + bw + 10, by + 34), (bx + bw, by + 42)] if mine else [
                (bx, by + 26), (bx - 10, by + 34), (bx, by + 42)]
            d.polygon(tip, fill=GREEN if mine else WHITE)
            for i, ln in enumerate(lines):
                _draw_text(d, (bx + 20, by + 13 + i * 42), ln)
            if typ == "voice" and t.get("transcript"):
                _draw_transcript(d, t["transcript"], ax, by + bh + 12, mine)
        y += h
    return img


def _draw_transcript(d: ImageDraw.ImageDraw, text: str, ax: int, ty: int, mine: bool) -> None:
    """WeChat 语音转文字: a light rounded box under the voice bubble, no tail, same side as the speaker."""
    lines = _wrap(text, BUBBLE_MAX - 40)
    tw = max(sum(_char_w(c) for c in ln) for ln in lines)
    bw, bh = tw + 36, len(lines) * 42 + 20
    bx = ax - 20 - bw if mine else ax + AVATAR + 20
    d.rounded_rectangle([bx, ty, bx + bw, ty + bh], radius=10, fill=(247, 247, 247), outline=(222, 222, 222))
    for i, ln in enumerate(lines):
        _draw_text(d, (bx + 18, ty + 10 + i * 42), ln)


GROUP_FILLERS = [
    {"speaker": "other", "nick": "Lily", "text": "哈哈哈周末见～"},
    {"speaker": "other", "nick": "陈姐", "text": "[表情]", "type": "sticker"},
]


def render_case(case: dict) -> list[Path]:
    shot = case["screenshot"]
    style = shot.get("style", "normal")
    nick = shot.get("client_display_name") or case["client"]["name"]
    turns = [dict(t) for t in case["dialog"]]
    for f in SHOTS_DIR.glob(f"{case['id']}_*.png"):
        f.unlink()

    group = style == "group_chat"
    if group:
        for t in turns:
            if t["speaker"] == "client":
                t["nick"] = nick
        mid = max(1, len(turns) // 2)
        turns = turns[:1] + [GROUP_FILLERS[0]] + turns[1:mid] + [GROUP_FILLERS[1]] + turns[mid:]
        title = "周末下午茶小群(5)"
    else:
        title = nick

    if style == "multi" and len(turns) >= 3:
        cut = len(turns) // 2 + 1
        parts = [turns[:cut], turns[cut - 1 :]]  # one overlapping message, like real scrolling captures
    else:
        parts = [turns]

    out = []
    for i, part in enumerate(parts, 1):
        img = render(part, title, group=group, client_nick=nick)
        if style == "blurry":
            small = img.resize((img.width // 2, img.height // 2), Image.BILINEAR)
            buf = io.BytesIO()
            small.save(buf, "JPEG", quality=35)
            img = Image.open(buf).resize(img.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))
        elif style == "cropped":
            top = 96 + int((img.height - 96) * 0.15)
            img = img.crop((0, top, W - 30, img.height))
        p = SHOTS_DIR / f"{case['id']}_{i}.png"
        img.convert("RGB").save(p)
        out.append(p)
    return out


def main() -> None:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ids = set(sys.argv[1:])
    n = 0
    for c in load_cases():
        if not c.get("screenshot") or (ids and c["id"] not in ids):
            continue
        paths = render_case(c)
        n += 1
        print(c["id"], c["screenshot"].get("style"), ", ".join(p.name for p in paths))
    print(f"rendered {n} cases → {SHOTS_DIR}")


if __name__ == "__main__":
    main()
