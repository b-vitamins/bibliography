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


def _ascii_words(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9, ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def author_signature(author_value: str | list[str]) -> str:
    if isinstance(author_value, list):
        value = " and ".join(author_value)
    else:
        value = author_value or ""
    people = [p.strip() for p in _ascii_words(value).split(" and ") if p.strip()]
    surnames: list[str] = []

    for person in people:
        if "," in person:
            left = person.split(",", 1)[0].strip()
            toks = [t for t in left.split() if t]
            if toks:
                surnames.append(toks[-1])
            continue
        toks = [t for t in person.split() if t]
        if toks:
            surnames.append(toks[-1])

    return " ".join(surnames)


def entry_signature(*, year: int | str, title: str, author: str | list[str]) -> str:
    year_str = str(year).strip()
    if year_str.isdigit():
        year_str = str(int(year_str))
    return f"{year_str}|{normalize_text(title)}|{author_signature(author)}"


def generate_bib_key(
    first_author: str,
    year: int,
    title: str,
    existing_keys: set[str],
    *,
    global_key_signatures: dict[str, set[str]] | None = None,
    candidate_signature: str | None = None,
) -> str:
    base = f"{_author_token(first_author)}{int(year)}{_keyword_token(title)}"
    if not base[0].isalpha():
        base = f"p{base}"
    candidate = base
    suffix = 0

    global_key_signatures = global_key_signatures or {}
    while True:
        if candidate in existing_keys:
            suffix += 1
            candidate = f"{base}{suffix}"
            continue

        signatures = global_key_signatures.get(candidate, set())
        if not signatures:
            break
        if candidate_signature and candidate_signature in signatures:
            break
        suffix += 1
        candidate = f"{base}{suffix}"

    existing_keys.add(candidate)
    if candidate_signature:
        global_key_signatures.setdefault(candidate, set()).add(candidate_signature)
    return candidate
