#!/usr/bin/env python3
"""Strict BibTeX linter for repository quality gates."""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
OPENREVIEW_FORUM_RE = re.compile(r"https?://openreview\.net/forum\?id=([^&#]+)", re.IGNORECASE)
OPENREVIEW_PDF_RE = re.compile(r"https?://openreview\.net/pdf\?id=([^&#]+)", re.IGNORECASE)
BIBKEY_RE = re.compile(r"^[a-z][a-z0-9]*\d{4}[a-z0-9]+$")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")

REQUIRED_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "inproceedings": ("author", "title", "booktitle", "year"),
    "article": ("author", "title", "journal", "year"),
    "book": ("author", "title", "publisher", "year"),
    "incollection": ("author", "title", "booktitle", "publisher", "year"),
    "phdthesis": ("author", "title", "school", "year"),
    "mastersthesis": ("author", "title", "school", "year"),
    "techreport": ("author", "title", "institution", "year"),
}


@dataclass
class Issue:
    file: str
    key: str | None
    severity: str
    code: str
    message: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lint BibTeX files with strict repository rules")
    p.add_argument("files", nargs="*", help="BibTeX files or glob patterns")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return non-zero when warnings are present",
    )
    p.add_argument(
        "--max-issues",
        type=int,
        default=0,
        help="Cap number of issues printed (0 = all)",
    )
    return p.parse_args()


def iter_bib_files(patterns: list[str]) -> list[Path]:
    if not patterns:
        roots = [
            "books",
            "collections",
            "conferences",
            "courses",
            "curated",
            "journals",
            "presentations",
            "references",
            "theses",
        ]
        patterns = [f"{root}/**/*.bib" for root in roots]

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
                    seen.add(rp)
                    found.append(p)
    return found


def parse_bib(path: Path) -> Any:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    data = path.read_text(encoding="utf-8")
    return bibtexparser.loads(data, parser=parser)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def normalize_title(s: str) -> str:
    text = (s or "").replace("{", "").replace("}", "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return normalize_spaces(text)


def extract_openreview_id(url: str) -> str:
    if not url:
        return ""
    m = OPENREVIEW_FORUM_RE.search(url)
    if m:
        return m.group(1)
    m = OPENREVIEW_PDF_RE.search(url)
    if m:
        return m.group(1)
    return ""


def looks_like_pdf_url(url: str) -> bool:
    u = (url or "").lower()
    return u.endswith(".pdf") or "/pdf?" in u or "arxiv.org/pdf/" in u


def has_field(entry: dict[str, Any], field: str) -> bool:
    return bool(str(entry.get(field, "")).strip())


def validate_key_format(key: str, year: str) -> list[str]:
    issues: list[str] = []
    if not key:
        return ["entry key is missing"]
    if key != key.lower():
        issues.append("entry key must be lowercase")
    if any(ch in key for ch in ("-", "_", ".")):
        issues.append("entry key must not contain '-', '_' or '.'")
    if not BIBKEY_RE.match(key):
        issues.append("entry key must follow <author><year><keyword> shape")
    if year and YEAR_RE.match(year):
        if year not in key:
            issues.append("entry key does not include entry year")
    return issues


def lint_entry(path: Path, entry: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    key = str(entry.get("ID", "")).strip()
    etype = str(entry.get("ENTRYTYPE", "")).strip().lower()
    year = str(entry.get("year", "")).strip()

    # Generic required-field validation by type.
    required = REQUIRED_FIELDS_BY_TYPE.get(etype)
    if required:
        missing = [field for field in required if not has_field(entry, field)]
        if missing:
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="missing_required_fields",
                    message=f"{etype} missing required fields: {', '.join(missing)}",
                )
            )

    if year and not YEAR_RE.match(year):
        issues.append(
            Issue(
                file=str(path),
                key=key or None,
                severity="error",
                code="invalid_year",
                message=f"year must be 4-digit in [1900,2099], got: {year}",
            )
        )

    for msg in validate_key_format(key, year):
        issues.append(
            Issue(
                file=str(path),
                key=key or None,
                severity="warning",
                code="key_format",
                message=msg,
            )
        )

    # URL checks for common link fields.
    for field in ("url", "pdf", "arxiv"):
        value = str(entry.get(field, "")).strip()
        if not value:
            continue
        if not HTTP_URL_RE.match(value):
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="invalid_url_scheme",
                    message=f"{field} must be HTTP(S): {value}",
                )
            )

    pdf = str(entry.get("pdf", "")).strip()
    if pdf and not looks_like_pdf_url(pdf):
        issues.append(
            Issue(
                file=str(path),
                key=key or None,
                severity="warning",
                code="pdf_field_suspicious",
                message=f"pdf field does not look like a PDF URL: {pdf}",
            )
        )

    arxiv = str(entry.get("arxiv", "")).strip().lower()
    if arxiv and "arxiv.org/abs/" not in arxiv:
        issues.append(
            Issue(
                file=str(path),
                key=key or None,
                severity="warning",
                code="arxiv_field_suspicious",
                message=f"arxiv field should point to arxiv.org/abs: {entry.get('arxiv')}",
            )
        )

    # Oral-specific rules.
    if path.parts[:2] == ("collections", "orals"):
        stem_year = path.stem
        if etype != "inproceedings":
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="oral_entry_type",
                    message="oral entry must be inproceedings",
                )
            )
        if not has_field(entry, "url"):
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="oral_missing_url",
                    message="oral entry missing required url field",
                )
            )
        if not has_field(entry, "pdf"):
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="oral_missing_pdf",
                    message="oral entry missing required pdf field",
                )
            )

        note = str(entry.get("note", "")).strip().lower()
        if note != "oral":
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="warning",
                    code="oral_note",
                    message="oral entry should have note={Oral}",
                )
            )

        if year and stem_year and year != stem_year:
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="oral_year_mismatch",
                    message=f"entry year {year} does not match file year {stem_year}",
                )
            )

        url = str(entry.get("url", "")).strip()
        pdf_url = str(entry.get("pdf", "")).strip()
        rid_url = extract_openreview_id(url)
        rid_pdf = extract_openreview_id(pdf_url)
        if (rid_url and not rid_pdf) or (rid_pdf and not rid_url):
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="warning",
                    code="oral_mixed_openreview_links",
                    message="url/pdf fields mix OpenReview and non-OpenReview links",
                )
            )
        if rid_url and rid_pdf and rid_url != rid_pdf:
            issues.append(
                Issue(
                    file=str(path),
                    key=key or None,
                    severity="error",
                    code="oral_openreview_id_mismatch",
                    message=f"url id ({rid_url}) and pdf id ({rid_pdf}) differ",
                )
            )

    return issues


def lint_file(path: Path) -> tuple[int, list[Issue]]:
    issues: list[Issue] = []
    try:
        db = parse_bib(path)
    except Exception as ex:
        return 0, [
            Issue(
                file=str(path),
                key=None,
                severity="error",
                code="parse_error",
                message=f"failed to parse: {ex}",
            )
        ]

    entries = db.entries
    key_map: dict[str, int] = {}
    title_map: dict[str, int] = {}

    for entry in entries:
        key = str(entry.get("ID", "")).strip()
        if key:
            key_map[key] = key_map.get(key, 0) + 1
        title_norm = normalize_title(str(entry.get("title", "")))
        if title_norm:
            title_map[title_norm] = title_map.get(title_norm, 0) + 1
        issues.extend(lint_entry(path, entry))

    for key, count in sorted(key_map.items()):
        if count > 1:
            issues.append(
                Issue(
                    file=str(path),
                    key=key,
                    severity="error",
                    code="duplicate_key_in_file",
                    message=f"duplicate key appears {count} times in file",
                )
            )

    for title_norm, count in sorted(title_map.items()):
        if count > 1:
            issues.append(
                Issue(
                    file=str(path),
                    key=None,
                    severity="warning",
                    code="duplicate_title_in_file",
                    message=f"duplicate normalized title appears {count} times: {title_norm}",
                )
            )

    return len(entries), issues


def print_text_summary(files: int, entries: int, issues: list[Issue], max_issues: int) -> None:
    by_sev: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for issue in issues:
        by_sev[issue.severity] = by_sev.get(issue.severity, 0) + 1
        by_code[issue.code] = by_code.get(issue.code, 0) + 1

    print(f"files_scanned: {files}")
    print(f"entries_scanned: {entries}")
    print(f"issues_found: {len(issues)}")
    if by_sev:
        print("issues_by_severity:")
        for sev in sorted(by_sev):
            print(f"  {sev}: {by_sev[sev]}")
    if by_code:
        print("issues_by_code:")
        for code in sorted(by_code):
            print(f"  {code}: {by_code[code]}")

    to_show = issues if max_issues <= 0 else issues[:max_issues]
    for issue in to_show:
        k = issue.key or "-"
        print(f"[{issue.severity}] {issue.file} :: {k} :: {issue.code} :: {issue.message}")

    hidden = len(issues) - len(to_show)
    if hidden > 0:
        print(f"... {hidden} additional issues hidden (use --max-issues 0 to show all)")


def main() -> int:
    args = parse_args()
    files = iter_bib_files(args.files)
    if not files:
        print("No .bib files found for linting.", file=sys.stderr)
        return 1

    all_issues: list[Issue] = []
    total_entries = 0
    for path in files:
        entries, issues = lint_file(path)
        total_entries += entries
        all_issues.extend(issues)

    if args.json:
        payload = {
            "files_scanned": len(files),
            "entries_scanned": total_entries,
            "issues_found": len(all_issues),
            "issues": [asdict(i) for i in all_issues],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text_summary(len(files), total_entries, all_issues, args.max_issues)

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    if error_count > 0:
        return 2
    if args.fail_on_warning and warning_count > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
