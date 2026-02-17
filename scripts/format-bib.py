#!/usr/bin/env python3
"""Deterministic BibTeX formatter for stable diffs."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode

DEFAULT_FIELD_ORDER = [
    "author",
    "title",
    "booktitle",
    "journal",
    "editor",
    "series",
    "volume",
    "number",
    "pages",
    "publisher",
    "address",
    "organization",
    "institution",
    "school",
    "month",
    "year",
    "note",
    "doi",
    "url",
    "pdf",
    "openalex",
    "eprint",
    "archiveprefix",
    "primaryclass",
    "arxiv",
    "file",
    "abstract",
    "keywords",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Format BibTeX files deterministically")
    p.add_argument("files", nargs="+", help="BibTeX files or glob patterns")
    p.add_argument("--check", action="store_true", help="Check formatting without writing files")
    p.add_argument(
        "--sort-by",
        choices=("key", "year", "none"),
        default="key",
        help="Entry sorting strategy (default: key)",
    )
    p.add_argument(
        "--trailing-comma",
        action="store_true",
        help="Write trailing commas for fields",
    )
    p.add_argument(
        "--line-width",
        type=int,
        default=100,
        help="Target line width for wrapped values (default: 100)",
    )
    return p.parse_args()


def iter_bib_files(patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        matches = [Path(x) for x in sorted(glob.glob(pattern, recursive=True))]
        if not matches:
            p = Path(pattern)
            if p.exists():
                matches = [p]
        for p in matches:
            if p.is_file() and p.suffix.lower() == ".bib":
                rp = p.resolve()
                if rp not in seen:
                    found.append(p)
                    seen.add(rp)
    return found


def load_bib(path: Path) -> Any:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    text = path.read_text(encoding="utf-8")
    return text, bibtexparser.loads(text, parser=parser)


def sort_entries(entries: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    if sort_by == "none":
        return entries
    if sort_by == "year":
        def keyfn(e: dict[str, Any]) -> tuple[str, str]:
            year = str(e.get("year", "")).strip()
            entry_id = str(e.get("ID", "")).strip().lower()
            return (year, entry_id)
        return sorted(entries, key=keyfn)

    return sorted(entries, key=lambda e: str(e.get("ID", "")).strip().lower())


def reorder_entry_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a new entry dict with stable field ordering."""
    out: dict[str, Any] = {}
    for fixed in ("ENTRYTYPE", "ID"):
        if fixed in entry:
            out[fixed] = entry[fixed]

    for field in DEFAULT_FIELD_ORDER:
        if field in entry:
            out[field] = entry[field]

    remaining = [k for k in entry.keys() if k not in out]
    for field in sorted(remaining):
        out[field] = entry[field]

    return out


def format_bib(db: Any, sort_by: str, trailing_comma: bool, line_width: int) -> str:
    db.entries = [reorder_entry_fields(e) for e in sort_entries(list(db.entries), sort_by)]

    writer = BibTexWriter()
    writer.indent = "  "
    writer.align_values = False
    writer.add_trailing_comma = trailing_comma
    writer.order_entries_by = None
    writer.display_order = tuple(DEFAULT_FIELD_ORDER)
    writer.comma_first = False
    writer.entry_separator = "\n\n"
    writer.contents = ["comments", "preambles", "strings", "entries"]
    writer._max_line_width = line_width  # pylint: disable=protected-access

    text = writer.write(db)
    if not text.endswith("\n"):
        text += "\n"
    return text


def main() -> int:
    args = parse_args()
    files = iter_bib_files(args.files)
    if not files:
        print("No .bib files matched")
        return 1

    changed: list[Path] = []
    for path in files:
        original_text, db = load_bib(path)
        formatted = format_bib(
            db=db,
            sort_by=args.sort_by,
            trailing_comma=args.trailing_comma,
            line_width=args.line_width,
        )
        if formatted != original_text:
            changed.append(path)
            if not args.check:
                path.write_text(formatted, encoding="utf-8")

    if args.check:
        if changed:
            for p in changed:
                print(f"would reformat: {p}")
            print(f"files_needing_format: {len(changed)}")
            return 2
        print("all files already formatted")
        return 0

    print(f"formatted_files: {len(changed)}")
    for p in changed:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
