#!/usr/bin/env python3
"""Coverage dashboard for BibTeX metadata completeness."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

DEFAULT_FIELDS = ["url", "pdf", "arxiv", "doi", "abstract", "file"]


@dataclass
class StatRow:
    scope: str
    entries: int
    present: dict[str, int]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report BibTeX metadata coverage")
    p.add_argument("files", nargs="*", help="BibTeX files or glob patterns")
    p.add_argument(
        "--fields",
        default=",".join(DEFAULT_FIELDS),
        help=f"Comma-separated fields to report (default: {','.join(DEFAULT_FIELDS)})",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON report")
    p.add_argument("--output", default="", help="Optional output path for report")
    p.add_argument(
        "--only-orals",
        action="store_true",
        help="Restrict to collections/orals/*.bib",
    )
    return p.parse_args()


def iter_bib_files(patterns: list[str], only_orals: bool) -> list[Path]:
    if not patterns:
        if only_orals:
            patterns = ["collections/orals/**/*.bib"]
        else:
            roots = [
                "books",
                "collections",
                "conferences",
                "courses",
                "journals",
                "presentations",
                "references",
                "theses",
            ]
            patterns = [f"{r}/**/*.bib" for r in roots]

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
                if only_orals and p.parts[:2] != ("collections", "orals"):
                    continue
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    found.append(p)
    return found


def load_entries(path: Path) -> list[dict[str, Any]]:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    text = path.read_text(encoding="utf-8")
    try:
        db = bibtexparser.loads(text, parser=parser)
    except Exception:
        fallback = BibTexParser(common_strings=True)
        fallback.ignore_nonstandard_types = False
        db = bibtexparser.loads(text, parser=fallback)
    return list(db.entries)


def classify_conference_year(path: Path) -> str:
    parts = path.parts
    if len(parts) >= 4 and parts[0] == "collections" and parts[1] == "orals":
        conf = parts[2]
        year = path.stem
        return f"orals/{conf}/{year}"
    if len(parts) >= 3 and parts[0] == "conferences":
        conf = parts[1]
        year = path.stem
        return f"conferences/{conf}/{year}"
    parent = str(path.parent)
    if parent.startswith("/"):
        parent = f"absolute:{parent}"
    return f"other/{parent}"


def init_counter(fields: list[str]) -> dict[str, int]:
    return {f: 0 for f in fields}


def has_value(entry: dict[str, Any], field: str) -> bool:
    return bool(str(entry.get(field, "")).strip())


def pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return (100.0 * part) / whole


def format_row(row: StatRow, fields: list[str]) -> str:
    pieces = [f"{row.scope}", f"entries={row.entries}"]
    for field in fields:
        count = row.present[field]
        pieces.append(f"{field}={count} ({pct(count, row.entries):.1f}%)")
    return " | ".join(pieces)


def main() -> int:
    args = parse_args()
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    if not fields:
        print("No fields requested", file=sys.stderr)
        return 1

    files = iter_bib_files(args.files, args.only_orals)
    if not files:
        print("No .bib files matched", file=sys.stderr)
        return 1

    by_file: list[StatRow] = []
    by_group: dict[str, StatRow] = {}
    total = StatRow(scope="TOTAL", entries=0, present=init_counter(fields))

    for path in files:
        entries = load_entries(path)
        file_stat = StatRow(scope=str(path), entries=len(entries), present=init_counter(fields))

        group = classify_conference_year(path)
        if group not in by_group:
            by_group[group] = StatRow(scope=group, entries=0, present=init_counter(fields))

        for entry in entries:
            for field in fields:
                if has_value(entry, field):
                    file_stat.present[field] += 1
                    by_group[group].present[field] += 1
                    total.present[field] += 1

        by_file.append(file_stat)
        by_group[group].entries += len(entries)
        total.entries += len(entries)

    payload = {
        "fields": fields,
        "files_scanned": len(files),
        "total": {
            "entries": total.entries,
            "present": total.present,
            "coverage_pct": {f: round(pct(total.present[f], total.entries), 2) for f in fields},
        },
        "by_group": [
            {
                "scope": row.scope,
                "entries": row.entries,
                "present": row.present,
                "coverage_pct": {f: round(pct(row.present[f], row.entries), 2) for f in fields},
            }
            for row in sorted(by_group.values(), key=lambda r: r.scope)
        ],
        "by_file": [
            {
                "scope": row.scope,
                "entries": row.entries,
                "present": row.present,
                "coverage_pct": {f: round(pct(row.present[f], row.entries), 2) for f in fields},
            }
            for row in sorted(by_file, key=lambda r: r.scope)
        ],
    }

    if args.json:
        out = json.dumps(payload, indent=2, sort_keys=True)
    else:
        lines = [
            f"files_scanned: {len(files)}",
            format_row(total, fields),
            "",
            "coverage_by_conference_year:",
        ]
        for row in sorted(by_group.values(), key=lambda r: r.scope):
            lines.append(format_row(row, fields))
        lines.append("")
        lines.append("coverage_by_file:")
        for row in sorted(by_file, key=lambda r: r.scope):
            lines.append(format_row(row, fields))
        out = "\n".join(lines) + "\n"

    if args.output:
        op = Path(args.output)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(out, encoding="utf-8")
    else:
        print(out, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
