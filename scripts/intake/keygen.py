from __future__ import annotations

import re
import unicodedata

from core.normalization import normalize_text

_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _ascii_alnum(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _author_token(author: str) -> str:
    value = (author or "").strip()
    if not value:
        return "paper"
    if "," in value:
        value = value.split(",", 1)[0].strip()
    parts = [p for p in re.split(r"\s+", value) if p]
    token = _ascii_alnum(parts[-1] if parts else value)
    return token or "paper"


def _keyword_token(title: str) -> str:
    words = [w for w in normalize_text(title).split() if w]
    for word in words:
        if len(word) <= 2:
            continue
        if word in _STOPWORDS:
            continue
        token = _ascii_alnum(word)
        if token:
            return token
    for word in words:
        token = _ascii_alnum(word)
        if token:
            return token
    return "paper"


def generate_bib_key(first_author: str, year: int, title: str, existing_keys: set[str]) -> str:
    base = f"{_author_token(first_author)}{int(year)}{_keyword_token(title)}"
    if not base[0].isalpha():
        base = f"p{base}"
    candidate = base
    suffix = 0
    while candidate in existing_keys:
        suffix += 1
        candidate = f"{base}{suffix}"
    existing_keys.add(candidate)
    return candidate

