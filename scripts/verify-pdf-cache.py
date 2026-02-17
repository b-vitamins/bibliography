#!/usr/bin/env python3
"""Verify local PDF cache referenced from BibTeX `file` fields."""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

PDF_HEADER = b"%PDF-"


@dataclass
class Issue:
    file: str
    key: str | None
    severity: str
    code: str
    message: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify local cached PDFs referenced by BibTeX entries")
    p.add_argument("files", nargs="+", help="BibTeX files or glob patterns")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return non-zero if warnings are present",
    )
    p.add_argument(
        "--strict-title-match",
        action="store_true",
        help="Treat title-mismatch checks as errors instead of warnings",
    )
    p.add_argument(
        "--max-issues",
        type=int,
        default=0,
        help="Cap number of issues printed (0 = all)",
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
                    seen.add(rp)
                    found.append(p)
    return found


def parse_bib(path: Path) -> Any:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    text = path.read_text(encoding="utf-8")
    return bibtexparser.loads(text, parser=parser)


def normalize_text(s: str) -> str:
    text = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("{", "").replace("}", "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def title_similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(a=na, b=nb).ratio()


def extract_paths_from_file_field(raw: str) -> list[Path]:
    """Parse Zotero-like `file` field formats into PDF paths."""
    if not raw:
        return []

    paths: list[Path] = []
    for chunk in [c.strip() for c in raw.split(";") if c.strip()]:
        item = chunk
        if item.startswith(":"):
            item = item[1:]

        # Handle common ':pdf' suffix labels.
        lowered = item.lower()
        if lowered.endswith(":pdf"):
            item = item[:-4]
        elif ":" in item:
            head, tail = item.rsplit(":", 1)
            if tail.lower() in {"pdf", "application/pdf"}:
                item = head

        if item.lower().endswith(".pdf"):
            paths.append(Path(item))

    # Deduplicate while preserving order.
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def read_pdf_metadata_title(path: Path) -> str:
    """Best-effort metadata title extraction from raw PDF bytes.

    This intentionally avoids optional third-party PDF parsers so the script runs
    in minimal environments.
    """
    try:
        data = path.read_bytes()
    except Exception:
        return ""

    # Search document info dictionary title.
    # This is heuristic and may fail for compressed object streams.
    text = data[:2_000_000].decode("latin-1", errors="ignore")
    m = re.search(r"/Title\s*\((.{1,500}?)\)", text, flags=re.DOTALL)
    if not m:
        return ""

    title = m.group(1)
    title = title.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    title = re.sub(r"\s+", " ", title).strip()
    return title


def metadata_title_plausible(title: str) -> bool:
    if not title:
        return False
    low = title.lower()
    bad_markers = ("/subject", "endobj", "xref", "flatedecode", "<<", ">>", "/length", "/type")
    if any(marker in low for marker in bad_markers):
        return False
    letters = sum(ch.isalpha() for ch in title)
    ratio = letters / max(1, len(title))
    words = re.findall(r"[A-Za-z]{2,}", title)
    if ratio < 0.55:
        return False
    if not (3 <= len(words) <= 40):
        return False
    return True


def verify_pdf_attachment(
    bib_path: Path,
    entry: dict[str, Any],
    attachment: Path,
    strict_title_match: bool,
) -> list[Issue]:
    issues: list[Issue] = []
    key = str(entry.get("ID", "")).strip() or None
    title = str(entry.get("title", "")).strip()

    if not attachment.is_absolute():
        attachment = (bib_path.parent / attachment).resolve()

    if not attachment.exists():
        return [
            Issue(
                file=str(bib_path),
                key=key,
                severity="error",
                code="pdf_missing",
                message=f"referenced PDF does not exist: {attachment}",
            )
        ]

    if not attachment.is_file():
        return [
            Issue(
                file=str(bib_path),
                key=key,
                severity="error",
                code="pdf_not_file",
                message=f"referenced PDF path is not a regular file: {attachment}",
            )
        ]

    size = attachment.stat().st_size
    if size < 1024:
        issues.append(
            Issue(
                file=str(bib_path),
                key=key,
                severity="error",
                code="pdf_too_small",
                message=f"PDF is suspiciously small ({size} bytes): {attachment}",
            )
        )

    try:
        with attachment.open("rb") as f:
            header = f.read(len(PDF_HEADER))
    except Exception as ex:
        issues.append(
            Issue(
                file=str(bib_path),
                key=key,
                severity="error",
                code="pdf_unreadable",
                message=f"unable to read PDF: {attachment} ({ex})",
            )
        )
        return issues

    if header != PDF_HEADER:
        issues.append(
            Issue(
                file=str(bib_path),
                key=key,
                severity="error",
                code="pdf_bad_header",
                message=f"file is not a valid PDF signature (%PDF-): {attachment}",
            )
        )

    metadata_title = read_pdf_metadata_title(attachment)
    if not metadata_title_plausible(metadata_title):
        metadata_title = ""
    if metadata_title and title:
        sim = title_similarity(title, metadata_title)
        if sim < 0.45:
            severity = "error" if strict_title_match else "warning"
            issues.append(
                Issue(
                    file=str(bib_path),
                    key=key,
                    severity=severity,
                    code="pdf_title_mismatch",
                    message=(
                        "PDF metadata title appears to mismatch entry title "
                        f"(similarity={sim:.2f})"
                    ),
                )
            )
    elif title:
        # Fallback heuristic if metadata title is unavailable.
        stem_lower = attachment.stem.lower()
        if not (key and key.lower() in stem_lower):
            issues.append(
                Issue(
                    file=str(bib_path),
                    key=key,
                    severity="warning",
                    code="pdf_title_unverifiable",
                    message=(
                        "could not verify PDF title from metadata or filename; "
                        f"path={attachment}"
                    ),
                )
            )

    return issues


def verify_file(path: Path, strict_title_match: bool) -> tuple[int, list[Issue]]:
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
                message=f"failed to parse BibTeX: {ex}",
            )
        ]

    entries = list(db.entries)
    for entry in entries:
        key = str(entry.get("ID", "")).strip() or None
        raw_file = str(entry.get("file", "")).strip()
        if not raw_file:
            issues.append(
                Issue(
                    file=str(path),
                    key=key,
                    severity="warning",
                    code="missing_file_field",
                    message="entry has no local file attachment",
                )
            )
            continue

        attachments = extract_paths_from_file_field(raw_file)
        if not attachments:
            issues.append(
                Issue(
                    file=str(path),
                    key=key,
                    severity="warning",
                    code="file_field_no_pdf_path",
                    message=f"file field had no parseable PDF path: {raw_file}",
                )
            )
            continue

        for attachment in attachments:
            issues.extend(verify_pdf_attachment(path, entry, attachment, strict_title_match))

    return len(entries), issues


def print_summary(files_scanned: int, entries_scanned: int, issues: list[Issue], max_issues: int) -> None:
    by_sev: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for issue in issues:
        by_sev[issue.severity] = by_sev.get(issue.severity, 0) + 1
        by_code[issue.code] = by_code.get(issue.code, 0) + 1

    print(f"files_scanned: {files_scanned}")
    print(f"entries_scanned: {entries_scanned}")
    print(f"issues_found: {len(issues)}")
    if by_sev:
        print("issues_by_severity:")
        for sev in sorted(by_sev):
            print(f"  {sev}: {by_sev[sev]}")
    if by_code:
        print("issues_by_code:")
        for code in sorted(by_code):
            print(f"  {code}: {by_code[code]}")

    shown = issues if max_issues <= 0 else issues[:max_issues]
    for issue in shown:
        print(f"[{issue.severity}] {issue.file} :: {issue.key or '-'} :: {issue.code} :: {issue.message}")

    hidden = len(issues) - len(shown)
    if hidden > 0:
        print(f"... {hidden} additional issues hidden (use --max-issues 0 to show all)")


def main() -> int:
    args = parse_args()
    files = iter_bib_files(args.files)
    if not files:
        print("No .bib files matched", file=sys.stderr)
        return 1

    total_entries = 0
    all_issues: list[Issue] = []
    for path in files:
        entries, issues = verify_file(path, strict_title_match=args.strict_title_match)
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
        print_summary(len(files), total_entries, all_issues, args.max_issues)

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    if error_count > 0:
        return 2
    if args.fail_on_warning and warning_count > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
