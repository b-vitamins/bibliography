from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode


def resolve_bib_paths(paths_or_globs: list[str]) -> list[Path]:
    out: set[Path] = set()
    for item in paths_or_globs:
        matched = glob.glob(item)
        if matched:
            for path in matched:
                p = Path(path)
                if p.exists() and p.is_file() and p.suffix.lower() == ".bib":
                    out.add(p)
            continue
        p = Path(item)
        if p.exists() and p.is_file() and p.suffix.lower() == ".bib":
            out.add(p)
    return sorted(out)


def parse_bib_file(path: Path) -> bibtexparser.bibdatabase.BibDatabase:
    text = path.read_text(encoding="utf-8")
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode  # type: ignore[attr-defined]
    parser.ignore_nonstandard_types = False
    try:
        return bibtexparser.loads(text, parser=parser)
    except Exception:
        fallback = BibTexParser(common_strings=True)
        fallback.ignore_nonstandard_types = False
        return bibtexparser.loads(text, parser=fallback)


def entry_key(entry: dict[str, Any]) -> str:
    return str(entry.get("ID", "")).strip()


def entry_type(entry: dict[str, Any]) -> str:
    return str(entry.get("ENTRYTYPE", "")).strip().lower()


def get_entry_map(db: bibtexparser.bibdatabase.BibDatabase) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in db.entries:
        key = entry_key(entry)
        if key:
            out[key] = entry
    return out


def write_bib_file(path: Path, db: bibtexparser.bibdatabase.BibDatabase) -> None:
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.display_order = [
        "author",
        "title",
        "booktitle",
        "journal",
        "publisher",
        "year",
        "volume",
        "number",
        "pages",
        "doi",
        "url",
        "pdf",
        "abstract",
        "note",
        "file",
    ]
    rendered = writer.write(db)
    path.write_text(rendered, encoding="utf-8")
