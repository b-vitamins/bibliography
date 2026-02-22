from __future__ import annotations

import datetime as dt
import hashlib


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def text_sha256(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()

