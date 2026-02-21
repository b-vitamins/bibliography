from __future__ import annotations

import html
import re
import unicodedata


def strip_latex(value: str) -> str:
    text = value or ""
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\&", "&")
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    return text.replace("\\", " ")


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_text(value: str) -> str:
    text = html.unescape(value or "")
    text = strip_latex(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return normalize_spaces(text)


def equivalent_text(left: str, right: str) -> bool:
    return normalize_text(left) == normalize_text(right)


def is_prefix_equivalent(left: str, right: str) -> bool:
    a = normalize_text(left)
    b = normalize_text(right)
    return bool(a and b and (a.startswith(b) or b.startswith(a)))


def word_count(value: str) -> int:
    return len(normalize_spaces(value).split()) if value else 0
