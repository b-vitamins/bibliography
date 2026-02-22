"""Shared pipeline primitives for enrichment and intake workflows."""

from .http_client import CachedHttpClient, HttpResponse
from .bibtex_io import (
    BibWriteIntegrityError,
    WriteFailureArtifacts,
    entry_key,
    entry_type,
    get_entry_map,
    parse_bib_file,
    parse_bib_text,
    resolve_bib_paths,
    transactional_write_bib_file,
    write_bib_file,
)
from .normalization import (
    equivalent_text,
    is_prefix_equivalent,
    normalize_spaces,
    normalize_text,
    sanitize_bibtex_text,
    strip_latex,
    word_count,
)
from .time_utils import now_iso, text_sha256

__all__ = [
    "CachedHttpClient",
    "HttpResponse",
    "BibWriteIntegrityError",
    "WriteFailureArtifacts",
    "entry_key",
    "entry_type",
    "get_entry_map",
    "parse_bib_file",
    "parse_bib_text",
    "resolve_bib_paths",
    "transactional_write_bib_file",
    "write_bib_file",
    "equivalent_text",
    "is_prefix_equivalent",
    "normalize_spaces",
    "normalize_text",
    "sanitize_bibtex_text",
    "strip_latex",
    "word_count",
    "now_iso",
    "text_sha256",
]
