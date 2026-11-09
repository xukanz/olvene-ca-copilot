"""Deterministic conversation state (brand_guide §4.1): who spoke last, how long ago,
whether the CA owes a reply, whether the client was already addressed.
Computed in code so the model does not have to do date arithmetic."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..schemas import Client, DialogTurn

_MD = re.compile(r"(?P<m>\d{1,2})[-/月](?P<d>\d{1,2})日?\s*(?:[^\d]{0,4})?(?P<h>\d{1,2})?[:：]?(?P<mi>\d{2})?")
_REL = re.compile(r"^(?P<w>今天|昨天|前天)\s*(?:[^\d]{0,4})?(?P<h>\d{1,2})?[:：]?(?P<mi>\d{2})?")
# Courtesy closers ("好的谢谢～") end a thread; they do not leave the CA owing a reply.
_CLOSER = re.compile(r"^\s*(好的?|好嘞|嗯+|哦+|OK|ok|收到|谢谢|多谢|感谢|辛苦了|[\U0001F000-\U0001FAFF👌🙏])[\s，,。.!！~～谢您了啦呀哈😊🙏👌]*$")
STALE_DAYS = 7  # after this long a new message re-opens the conversation rather than "replying late"
_TIME_ONLY = re.compile(r"^(?:[^\d]{0,4})?(?P<h>\d{1,2})[:：](?P<mi>\d{2})$")


def parse_time(t: str | None, today: date) -> datetime | None:
    if not t:
        return None
    t = t.strip()
    m = _REL.match(t)
    if m:
        d = today - timedelta(days={"今天": 0, "昨天": 1, "前天": 2}[m.group("w")])
        return datetime(d.year, d.month, d.day, int(m.group("h") or 12), int(m.group("mi") or 0))
    m = _MD.search(t)
    if m:
        mo, dd = int(m.group("m")), int(m.group("d"))
        yr = today.year if (mo, dd) <= (today.month, today.day) else today.year - 1
        try:
            return datetime(yr, mo, dd, int(m.group("h") or 12), int(m.group("mi") or 0))
        except ValueError:
            return None
    m = _TIME_ONLY.match(t)
    if m:
        return datetime(today.year, today.month, today.day, int(m.group("h")), int(m.group("mi")))
    return None


@dataclass
class DialogState:
    has_dialog: bool
    last_speaker: str | None  # "client" | "ca" | None
    days_since_last: int | None
    ongoing: bool  # same-day conversation in progress
    ca_owes_reply: bool  # client spoke last and is waiting
    reply_delayed: bool  # ... and has waited a day or more
    addressed_before: bool  # CA already used the client's name in this conversation
    text: str  # Chinese summary for the prompt

    @property
    def omit_salutation(self) -> bool:
        return self.ongoing and self.addressed_before


def compute_state(dialog: list[DialogTurn], client: Client, today_s: str) -> DialogState:
    today = date.fromisoformat(today_s)
    turns = [t for t in dialog if t.speaker in ("client", "ca")]
    if not turns:
        return DialogState(False, None, None, False, False, False, False,
                           "没有对话记录：这是 CA 主动发起的一条消息，以称呼开头。不要为“隔了很久才联系”道歉。")

    last = turns[-1]
    last_dt = None
    for t in reversed(turns):  # time may only be on some turns
        last_dt = parse_time(t.time, today)
        if last_dt:
            break
    if last_dt is None and client.last_interaction:  # e.g. a cropped screenshot lost the time separator
        m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", client.last_interaction.strip())
        if m:
            last_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0)
    days = (today - last_dt.date()).days if last_dt else None
    ongoing = days == 0
    closed = last.speaker == "client" and (bool(_CLOSER.match(last.text)) or last.type in ("sticker",))
    stale = days is not None and days >= STALE_DAYS
    owes = last.speaker == "client" and not closed and not stale
    delayed = owes and days is not None and days >= 1
    names = [n for n in (client.name, client.preferred_name) if n]
    surname = client.name[:1] if client.name else ""
    addressed = any(
        t.speaker == "ca" and (any(n in t.text for n in names) or (surname and re.search(f"{surname}(女士|先生|小姐)", t.text)))
        for t in turns
    )

    parts = [f"最后一条消息由{'客户' if last.speaker == 'client' else 'CA'}发出"]
    if closed:
        parts.append("是礼貌性的结束语，客户并不在等回复")
    if days is None:
        parts.append("时间未知")
    elif days == 0:
        parts.append("就在今天，对话正在进行中")
    else:
        parts.append(f"距今天 {days} 天")
    rules = []
    if ongoing and addressed:
        rules.append("CA 之前已经称呼过客户，这条消息是对话的下一句：不要以称呼开头，直接接话")
    else:
        rules.append("以称呼开头")
    if delayed:
        rules.append(f"客户的消息已经等了 {days} 天没有回复：每条都先为回复晚了道歉或简短解释，再回应内容")
    elif owes:
        rules.append("客户在等 CA 回复：先回应客户最后说的内容")
    elif stale and last.speaker == "client":
        rules.append("距客户上一条消息已较久，这条消息是重新开启对话，不必为回复晚道歉；客户上次提到的事如果仍然重要（情绪、近况），要自然地回应")
    if not delayed:
        rules.append("客户没有在等回复：不要为“回复晚”或“隔了很久才联系”道歉")
    text = "，".join(parts) + "。\n" + "\n".join(f"- {r}" for r in rules)
    return DialogState(True, last.speaker, days, ongoing, owes, delayed, addressed, text)
