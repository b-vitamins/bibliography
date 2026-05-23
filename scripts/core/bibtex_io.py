from __future__ import annotations

import copy
import glob
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import citerra


DEFAULT_FIELD_ORDER = [
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


@dataclass
class BibDatabase:
    entries: list[dict[str, Any]] = field(default_factory=list)
    comments: list[Any] = field(default_factory=list)
    preambles: list[Any] = field(default_factory=list)
    strings: list[tuple[str, Any]] = field(default_factory=list)
    document: Any | None = None
    source_text: str = ""

    _original_keys: list[str] = field(default_factory=list)
    _original_comments: list[Any] = field(default_factory=list)
    _original_preambles: list[Any] = field(default_factory=list)
    _original_strings: list[tuple[str, Any]] = field(default_factory=list)


@dataclass
class WriteFailureArtifacts:
    original_path: Path
    candidate_path: Path


class BibWriteIntegrityError(RuntimeError):
    def __init__(self, message: str, artifacts: WriteFailureArtifacts | None = None):
        super().__init__(message)
        self.artifacts = artifacts


def resolve_bib_paths(paths_or_globs: list[str]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for item in paths_or_globs:
        matched = sorted(glob.glob(item, recursive=True))
        if matched:
            for path in matched:
                p = Path(path).resolve()
                if p.exists() and p.is_file() and p.suffix.lower() == ".bib" and p not in seen:
                    seen.add(p)
                    out.append(p)
            continue
        p = Path(item).resolve()
        if p.exists() and p.is_file() and p.suffix.lower() == ".bib" and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _comment_records(document: Any) -> list[str]:
    return [str(getattr(comment, "raw", getattr(comment, "text", comment))) for comment in document.comments]


def _preamble_records(document: Any) -> list[Any]:
    return [getattr(preamble, "value", getattr(preamble, "raw", preamble)) for preamble in document.preambles]


def _string_records(document: Any) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for item in document.strings:
        name = str(getattr(item, "name", "")).strip()
        if name:
            out.append((name, getattr(item, "value", "")))
    return out


def parse_bib_text(text: str) -> BibDatabase:
    document = citerra.parse(
        text,
        tolerant=False,
        capture_source=True,
        preserve_raw=True,
        expand_values=True,
        latex_to_unicode=True,
    )
    entries = document.to_dicts()
    comments = _comment_records(document)
    preambles = _preamble_records(document)
    strings = _string_records(document)
    return BibDatabase(
        entries=entries,
        comments=comments,
        preambles=preambles,
        strings=strings,
        document=document,
        source_text=text,
        _original_keys=[entry_key(entry) for entry in entries],
        _original_comments=copy.deepcopy(comments),
        _original_preambles=copy.deepcopy(preambles),
        _original_strings=copy.deepcopy(strings),
    )


def parse_bib_file(path: Path) -> BibDatabase:
    return parse_bib_text(path.read_text(encoding="utf-8"))


def make_bib_database(
    entries: list[dict[str, Any]] | None = None,
    *,
    comments: list[Any] | None = None,
    preambles: list[Any] | None = None,
    strings: list[tuple[str, Any]] | dict[str, Any] | None = None,
) -> BibDatabase:
    parsed_strings = list(strings.items()) if isinstance(strings, dict) else list(strings or [])
    return BibDatabase(
        entries=list(entries or []),
        comments=list(comments or []),
        preambles=list(preambles or []),
        strings=parsed_strings,
    )


def entry_key(entry: dict[str, Any]) -> str:
    return str(entry.get("ID", "")).strip()


def entry_type(entry: dict[str, Any]) -> str:
    return str(entry.get("ENTRYTYPE", "")).strip().lower()


def get_entry_map(db: BibDatabase) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in db.entries:
        key = entry_key(entry)
        if key:
            out[key] = entry
    return out


def _can_preserve_raw(db: BibDatabase) -> bool:
    if db.document is None:
        return False
    if [entry_key(entry) for entry in db.entries] != db._original_keys:
        return False
    if db.comments != db._original_comments:
        return False
    if db.preambles != db._original_preambles:
        return False
    if db.strings != db._original_strings:
        return False
    return True


def render_bib_database(
    db: BibDatabase,
    *,
    field_order: list[str] | tuple[str, ...] | None = None,
    trailing_comma: bool = False,
    preserve_raw: bool = True,
    sort_by: list[str] | tuple[str, ...] | None = None,
    reverse: bool = False,
    entry_separator: str = "\n\n",
) -> str:
    order = list(field_order or DEFAULT_FIELD_ORDER)
    if preserve_raw and _can_preserve_raw(db):
        document = db.document
        document.update_from_dicts(db.entries)
        rendered = document.write(
            citerra.WriterConfig(
                preserve_raw=True,
                trailing_comma=trailing_comma,
                entry_separator=entry_separator,
            )
        )
    else:
        rendered = citerra.write_entries(
            db.entries,
            comments=db.comments,
            preambles=db.preambles,
            strings=db.strings,
            field_order=order,
            sort_by=sort_by,
            reverse=reverse,
            trailing_comma=trailing_comma,
            entry_separator=entry_separator,
        )
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def write_bib_file(path: Path, db: BibDatabase) -> None:
    path.write_text(render_bib_database(db), encoding="utf-8")


def transactional_write_bib_file(
    path: Path,
    db: BibDatabase,
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

    rendered = render_bib_database(db)

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
