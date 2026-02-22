from __future__ import annotations

import glob
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode


@dataclass
class WriteFailureArtifacts:
    original_path: Path
    candidate_path: Path


class BibWriteIntegrityError(RuntimeError):
    def __init__(self, message: str, artifacts: WriteFailureArtifacts | None = None):
        super().__init__(message)
        self.artifacts = artifacts


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


def parse_bib_text(text: str) -> bibtexparser.bibdatabase.BibDatabase:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode  # type: ignore[attr-defined]
    parser.ignore_nonstandard_types = False
    try:
        return bibtexparser.loads(text, parser=parser)
    except Exception:
        fallback = BibTexParser(common_strings=True)
        fallback.ignore_nonstandard_types = False
        return bibtexparser.loads(text, parser=fallback)


def parse_bib_file(path: Path) -> bibtexparser.bibdatabase.BibDatabase:
    text = path.read_text(encoding="utf-8")
    return parse_bib_text(text)


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


def _make_writer() -> BibTexWriter:
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
    return writer


def write_bib_file(path: Path, db: bibtexparser.bibdatabase.BibDatabase) -> None:
    writer = _make_writer()
    rendered = writer.write(db)
    path.write_text(rendered, encoding="utf-8")


def transactional_write_bib_file(
    path: Path,
    db: bibtexparser.bibdatabase.BibDatabase,
    baseline_entries: int,
    baseline_comments: int,
    max_comment_increase: int = 0,
    rollback_dir: Path | None = None,
) -> None:
    def _persist_failure_artifacts(temp_candidate: Path) -> WriteFailureArtifacts | None:
        if rollback_dir is None:
            temp_candidate.unlink(missing_ok=True)
            return None
        rollback_dir.mkdir(parents=True, exist_ok=True)
        stamp = uuid.uuid4().hex[:10]
        original_copy = rollback_dir / f"{path.stem}-{stamp}-original.bib"
        candidate_copy = rollback_dir / f"{path.stem}-{stamp}-candidate.bib"
        if path.exists():
            shutil.copy2(path, original_copy)
        else:
            original_copy.write_text("", encoding="utf-8")
        temp_candidate.replace(candidate_copy)
        return WriteFailureArtifacts(
            original_path=original_copy,
            candidate_path=candidate_copy,
        )

    writer = _make_writer()
    rendered = writer.write(db)

    temp_path = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex[:10]}"
    temp_path.write_text(rendered, encoding="utf-8")

    try:
        parsed = parse_bib_text(rendered)
    except Exception as exc:
        artifacts = _persist_failure_artifacts(temp_path)
        message = f"rendered bibtex parse validation failed: {exc}"
        if artifacts:
            message = (
                f"{message}; rollback_original={artifacts.original_path}; "
                f"rollback_candidate={artifacts.candidate_path}"
            )
        raise BibWriteIntegrityError(message, artifacts=artifacts) from exc
    entry_count = len(parsed.entries)
    comment_count = len(parsed.comments)

    reasons: list[str] = []
    if entry_count < baseline_entries:
        reasons.append(
            f"entry count dropped: baseline={baseline_entries} rendered={entry_count}"
        )
    allowed_comments = baseline_comments + max(0, max_comment_increase)
    if comment_count > allowed_comments:
        reasons.append(
            f"comment count increased unexpectedly: baseline={baseline_comments} "
            f"rendered={comment_count} allowed={allowed_comments}"
        )

    if reasons:
        artifacts = _persist_failure_artifacts(temp_path)
        details = "; ".join(reasons)
        if artifacts:
            details = (
                f"{details}; rollback_original={artifacts.original_path}; "
                f"rollback_candidate={artifacts.candidate_path}"
            )
        raise BibWriteIntegrityError(details, artifacts=artifacts)

    temp_path.replace(path)
