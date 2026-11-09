"""Daily usage caps for the public demo: per Google account and across all users.

Every LLM-backed action (parse screenshots, generate, regenerate) consumes one unit.
QUOTA_BACKEND=firestore keeps counters in Firestore so they survive restarts and are shared
by all Cloud Run instances; "memory" (default) is per-process and meant for local runs/tests.
"""
from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

USER_DAILY_LIMIT = int(os.environ.get("USER_DAILY_LIMIT", "20"))
GLOBAL_DAILY_LIMIT = int(os.environ.get("GLOBAL_DAILY_LIMIT", "200"))
QUOTA_TZ = ZoneInfo(os.environ.get("QUOTA_TZ", "Asia/Shanghai"))
QUOTA_BACKEND = os.environ.get("QUOTA_BACKEND", "memory")


class QuotaExceeded(Exception):
    pass


def _today() -> str:
    return datetime.now(QUOTA_TZ).date().isoformat()


class _MemoryQuota:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    def used(self, user: str) -> tuple[int, int]:
        d = _today()
        return self._counts[(d, user)], self._counts[(d, "*")]

    def consume(self, user: str) -> None:
        d = _today()
        with self._lock:
            if self._counts[(d, "*")] >= GLOBAL_DAILY_LIMIT:
                raise QuotaExceeded("今日全站额度已用完，请明天再试。")
            if self._counts[(d, user)] >= USER_DAILY_LIMIT:
                raise QuotaExceeded(f"你今天的 {USER_DAILY_LIMIT} 次额度已用完，请明天再试。")
            self._counts[(d, user)] += 1
            self._counts[(d, "*")] += 1


class _FirestoreQuota:
    def __init__(self) -> None:
        from google.cloud import firestore

        self._fs = firestore
        self._db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))
        self._col = self._db.collection(os.environ.get("QUOTA_COLLECTION", "olvene_usage"))

    def _refs(self, user: str):
        d = _today()
        return self._col.document(f"{d}__all"), self._col.document(f"{d}__{user}")

    def used(self, user: str) -> tuple[int, int]:
        g, u = self._refs(user)
        gs, us = g.get(), u.get()
        return (us.get("n") if us.exists else 0), (gs.get("n") if gs.exists else 0)

    def consume(self, user: str) -> None:
        g_ref, u_ref = self._refs(user)
        fs = self._fs

        @fs.transactional
        def txn(tx):
            g, u = g_ref.get(transaction=tx), u_ref.get(transaction=tx)
            gn, un = (g.get("n") if g.exists else 0), (u.get("n") if u.exists else 0)
            if gn >= GLOBAL_DAILY_LIMIT:
                raise QuotaExceeded("今日全站额度已用完，请明天再试。")
            if un >= USER_DAILY_LIMIT:
                raise QuotaExceeded(f"你今天的 {USER_DAILY_LIMIT} 次额度已用完，请明天再试。")
            now = fs.SERVER_TIMESTAMP
            tx.set(g_ref, {"n": gn + 1, "day": _today(), "updated": now})
            tx.set(u_ref, {"n": un + 1, "day": _today(), "user": user, "updated": now})

        txn(self._db.transaction())


_quota = None
_quota_lock = threading.Lock()


def get_quota():
    global _quota
    with _quota_lock:
        if _quota is None:
            _quota = _FirestoreQuota() if QUOTA_BACKEND == "firestore" else _MemoryQuota()
    return _quota
