from __future__ import annotations

import re
import unicodedata
from typing import Any

from .normalization import normalize_text

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
    "about",
    "against",
    "between",
    "during",
    "without",
    "under",
    "over",
    "via",
}

_GENERIC_KEYWORDS = {
    "paper",
    "article",
    "study",
    "research",
    "method",
    "approach",
}

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*\d{4}[a-z0-9]+$")


def _ascii_alnum(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _ascii_words(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9, ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_authors(author: str | list[str]) -> list[str]:
    if isinstance(author, list):
        value = " and ".join(author)
    else:
        value = author or ""
    return [part.strip() for part in value.split(" and ") if part.strip()]


def parse_key_parts(key: str) -> tuple[str, str, str] | None:
    value = (key or "").strip().lower()
    match = re.match(r"^([a-z][a-z0-9]*?)(\d{4})([a-z0-9]+)$", value)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def is_key_format_valid(key: str, *, expected_year: str | None = None) -> bool:
    issues = validate_bib_key(key, expected_year=expected_year)
    return len(issues) == 0


def validate_bib_key(key: str, *, expected_year: str | None = None) -> list[str]:
    issues: list[str] = []
    value = (key or "").strip()
    if not value:
        return ["missing key"]

    if value != value.lower():
        issues.append("contains uppercase letters")

    if re.search(r"[^a-zA-Z0-9]", value):
        issues.append("contains non-alphanumeric characters")

    parts = parse_key_parts(value)
    if parts is None:
        if not re.search(r"\d{4}", value):
            issues.append("missing 4-digit year")
        else:
            issues.append("must follow <author><year><keyword> shape")
        return issues

    _, year, keyword = parts
    if not keyword:
        issues.append("missing keyword after year")

    if expected_year:
        exp = str(expected_year).strip()
        if exp.isdigit() and len(exp) == 4 and exp != year:
            issues.append("key year does not match entry year")

    return issues


def author_token(author: str | list[str]) -> str:
    people = _split_authors(author)
    if not people:
        return "paper"

    first = people[0].strip()
    if "," in first:
        first = first.split(",", 1)[0].strip()

    parts = [p for p in re.split(r"\s+", first) if p]
    token = _ascii_alnum(parts[-1] if parts else first)
    return token or "paper"


def keyword_candidates(title: str, *, limit: int = 5) -> list[str]:
    words = [w for w in normalize_text(title).split() if w]

    out: list[str] = []
    seen: set[str] = set()

    for word in words:
        if len(word) <= 2 or word in _STOPWORDS:
            continue
        token = _ascii_alnum(word)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            return out

    for word in words:
        token = _ascii_alnum(word)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            return out

    return out


def keyword_token(title: str) -> str:
    candidates = keyword_candidates(title, limit=1)
    if candidates:
        return candidates[0]
    return "paper"


def suggest_bib_keys(
    *,
    author: str | list[str],
    year: int | str,
    title: str,
    limit: int = 3,
) -> list[str]:
    base_author = author_token(author)
    year_token = normalize_year(year)
    words = keyword_candidates(title, limit=max(3, limit * 2))

    out: list[str] = []
    for word in words:
        if word in _GENERIC_KEYWORDS:
            continue
        candidate = f"{base_author}{year_token}{word}"
        if candidate not in out:
            out.append(candidate)
        if len(out) >= limit:
            return out

    fallback = f"{base_author}{year_token}{keyword_token(title)}"
    if fallback not in out:
        out.append(fallback)
    return out[:limit]


def normalize_year(year: int | str) -> str:
    raw = str(year).strip()
    match = re.search(r"(19|20)\d{2}", raw)
    if match:
        return match.group(0)
    return "0000"


def author_signature(author_value: str | list[str]) -> str:
    people = [p.strip() for p in _ascii_words(" and ".join(_split_authors(author_value))).split(" and ") if p.strip()]
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
    return f"{normalize_year(year)}|{normalize_text(title)}|{author_signature(author)}"


def synthesize_bib_key(*, author: str | list[str], year: int | str, title: str) -> str:
    base = f"{author_token(author)}{normalize_year(year)}{keyword_token(title)}"
    base = _ascii_alnum(base)
    if not base:
        return "paper0000paper"
    if not base[0].isalpha():
        return f"p{base}"
    return base


def generate_bib_key(
    first_author: str,
    year: int | str,
    title: str,
    existing_keys: set[str],
    *,
    global_key_signatures: dict[str, set[str]] | None = None,
    candidate_signature: str | None = None,
) -> str:
    base = synthesize_bib_key(author=first_author, year=year, title=title)
    candidate = base
    suffix = 0

    signatures_map = global_key_signatures or {}
    while True:
        if candidate in existing_keys:
            suffix += 1
            candidate = f"{base}{suffix}"
            continue

        signatures = signatures_map.get(candidate, set())
        if not signatures:
            break
        if candidate_signature and candidate_signature in signatures:
            break

        suffix += 1
        candidate = f"{base}{suffix}"

    existing_keys.add(candidate)
    if candidate_signature:
        signatures_map.setdefault(candidate, set()).add(candidate_signature)
    return candidate


def key_expected_year(entry: dict[str, Any]) -> str:
    raw_year = normalize_year(str(entry.get("year", "")).strip())
    if raw_year != "0000":
        return raw_year
    key = str(entry.get("ID", "")).strip()
    parts = parse_key_parts(key)
    if parts is None:
        return "0000"
    return parts[1]
