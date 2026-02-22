from __future__ import annotations

from core.normalization import (
    equivalent_text,
    is_prefix_equivalent,
    normalize_spaces,
    normalize_text,
    sanitize_bibtex_text,
    strip_latex,
    word_count,
)

__all__ = [
    "strip_latex",
    "normalize_spaces",
    "normalize_text",
    "sanitize_bibtex_text",
    "equivalent_text",
    "is_prefix_equivalent",
    "word_count",
]

