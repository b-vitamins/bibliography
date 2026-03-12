#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from core.bibtex_io import (
    entry_key,
    entry_type,
    parse_bib_file,
    resolve_bib_paths,
    transactional_write_bib_file,
)

DEFAULT_DOCUMENTS_ROOT = Path("/home/b/documents")
DEFAULT_RUNS_ROOT = Path("/home/b/trash/research-notes-batch-runs")
REPO_ROOT = Path(__file__).resolve().parents[1]
ORALS_ROOT = (REPO_ROOT / "collections" / "orals").resolve()
CANONICAL_CONFERENCES_ROOT = (REPO_ROOT / "conferences").resolve()

TYPE_TO_DIR = {
    "article": "article",
    "inproceedings": "inproceedings",
    "phdthesis": "phdthesis",
    "mastersthesis": "mastersthesis",
    "book": "book",
    "incollection": "incollection",
    "inbook": "inbook",
    "proceedings": "proceedings",
    "techreport": "techreport",
    "unpublished": "unpublished",
    "misc": "misc",
    "online": "online",
    "manual": "manual",
    "booklet": "booklet",
    "conference": "conference",
    "phdproposal": "phdproposal",
    "masterthesis": "mastersthesis",
}

PUBLISHED_ARTIFACTS = {
    "reader-notes.md": ("notes", "reader-notes.md"),
    "reader-notes.json": ("notes", "reader-notes.json"),
    "fact-ledger.md": ("notes", "fact-ledger.md"),
    "validation-report.json": ("manifests", "validation-report.json"),
}

READY_FIELDS = [
    "job_id",
    "key",
    "entry_type",
    "title",
    "year",
    "selector_url",
    "selector_pdf",
    "arxiv_id",
    "arxiv_url",
    "workspace_dir",
    "notes_dir",
    "preferred_pdf_path",
    "existing_pdf_path",
    "source_bib_files",
    "target_bib_file",
]
SKIP_FIELDS = READY_FIELDS + ["reason"]

FINALIZE_FIELDS = [
    "key",
    "target_bib_file",
    "matched_entry_key",
    "match_mode",
    "notes_dir",
    "preferred_pdf_path",
    "pdf_action",
    "bib_action",
    "status",
    "error",
]

ARXIV_ID_RE = re.compile(r"([A-Za-z.-]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?$", re.IGNORECASE)
ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([A-Za-z.-]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)
ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.([A-Za-z.-]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?", re.IGNORECASE)
OPENREVIEW_ID_RE = re.compile(r"openreview\.net/(?:forum|pdf)\?id=([^&#]+)", re.IGNORECASE)
GENERIC_READTHROUGH_SUMMARY_RE = re.compile(r"^Read and indexed chunk C\d+$")
SPECIFIC_ANCHOR_RE = re.compile(r"\b(?:[A-Za-z0-9_.\-/]+):\d+(?:-\d+)?\b")
FACT_LEDGER_ANCHORED_BULLET_RE = re.compile(r"^\s*-\s+Anchor:\s+", re.MULTILINE)
SUCCESSFUL_WORKER_STATUSES = {"published", "ok", "success"}
REQUIRED_NOTE_JSON_STRING_FIELDS = ("title", "paper_type", "problem", "main_claim")
REQUIRED_NOTE_JSON_LIST_FIELDS = ("notation", "assumptions", "results", "limitations")


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def read_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing file: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"
    if not isinstance(raw, dict):
        return None, f"expected JSON object in {path}"
    return raw, None


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def coordinate_label_count(reader_notes_json: dict[str, Any]) -> int:
    coordinates = reader_notes_json.get("coordinates", {})
    if not isinstance(coordinates, dict):
        return 0
    total = 0
    for value in coordinates.values():
        if isinstance(value, list):
            total += sum(1 for item in value if nonempty_string(item))
    return total


def note_bundle_semantic_audit(
    *,
    reader_notes_md_path: Path,
    reader_notes_json_path: Path,
    fact_ledger_path: Path,
    validation_report_path: Path,
    readthrough_log_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []

    try:
        reader_notes_md = reader_notes_md_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        reader_notes_md = ""
        errors.append(f"missing file: {reader_notes_md_path}")

    try:
        fact_ledger = fact_ledger_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fact_ledger = ""
        errors.append(f"missing file: {fact_ledger_path}")

    validation_report, validation_error = read_json_file(validation_report_path)
    if validation_error:
        errors.append(validation_error)
    elif validation_report.get("passed") is not True:
        errors.append("validation report did not pass")
    elif validation_report.get("errors"):
        errors.append("validation report contains errors")

    reader_notes_json, reader_notes_error = read_json_file(reader_notes_json_path)
    if reader_notes_error:
        errors.append(reader_notes_error)
    elif reader_notes_json is not None:
        if reader_notes_json.get("tex_source_gate") != "PASS":
            errors.append("reader-notes.json tex_source_gate is not PASS")
        if reader_notes_json.get("readthrough_complete") is not True:
            errors.append("reader-notes.json readthrough_complete is not true")
        for field in REQUIRED_NOTE_JSON_STRING_FIELDS:
            if not nonempty_string(reader_notes_json.get(field)):
                errors.append(f"reader-notes.json missing substantive '{field}'")
        for field in REQUIRED_NOTE_JSON_LIST_FIELDS:
            value = reader_notes_json.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"reader-notes.json missing substantive '{field}' entries")
        if coordinate_label_count(reader_notes_json) < 3:
            errors.append("reader-notes.json has fewer than 3 coordinate labels")

    if fact_ledger and len(FACT_LEDGER_ANCHORED_BULLET_RE.findall(fact_ledger)) < 12:
        errors.append("fact-ledger.md has fewer than 12 anchored bullets")

    if reader_notes_md and len(SPECIFIC_ANCHOR_RE.findall(reader_notes_md)) < 10:
        errors.append("reader-notes.md has fewer than 10 specific anchor references")

    if readthrough_log_path is not None:
        readthrough_log, readthrough_error = read_json_file(readthrough_log_path)
        if readthrough_error:
            errors.append(readthrough_error)
        elif readthrough_log.get("completed") is not True:
            errors.append("readthrough log is incomplete")
        else:
            chunks = readthrough_log.get("chunks", [])
            if not isinstance(chunks, list) or not chunks:
                errors.append("readthrough log has no chunks")
            for index, chunk in enumerate(chunks, start=1):
                summary = str(chunk.get("summary", "")).strip()
                if not summary:
                    errors.append(f"readthrough chunk {index} has no summary")
                    continue
                if GENERIC_READTHROUGH_SUMMARY_RE.match(summary):
                    errors.append(f"readthrough chunk {index} uses a generic summary")

    return {
        "passed": not errors,
        "errors": errors,
    }


def workspace_note_bundle_audit(workspace: Path) -> dict[str, Any]:
    return note_bundle_semantic_audit(
        reader_notes_md_path=workspace / "notes" / "reader-notes.md",
        reader_notes_json_path=workspace / "notes" / "reader-notes.json",
        fact_ledger_path=workspace / "notes" / "fact-ledger.md",
        validation_report_path=workspace / "manifests" / "validation-report.json",
        readthrough_log_path=workspace / "manifests" / "readthrough-log.json",
    )


def published_note_bundle_audit(notes_dir: Path) -> dict[str, Any]:
    return note_bundle_semantic_audit(
        reader_notes_md_path=notes_dir / "reader-notes.md",
        reader_notes_json_path=notes_dir / "reader-notes.json",
        fact_ledger_path=notes_dir / "fact-ledger.md",
        validation_report_path=notes_dir / "validation-report.json",
        readthrough_log_path=None,
    )


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "batch"


def normalize_arxiv_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for matcher in (ARXIV_URL_RE, ARXIV_DOI_RE):
        match = matcher.search(text)
        if match:
            return match.group(1)
    plain = text.removeprefix("arXiv:").removeprefix("arxiv:").strip()
    match = ARXIV_ID_RE.match(plain)
    if match:
        return match.group(1)
    return None


def extract_arxiv_id(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    archive_prefix = str(entry.get("archiveprefix", "")).strip().lower()
    eprint = str(entry.get("eprint", "")).strip()
    if archive_prefix == "arxiv" and eprint:
        normalized = normalize_arxiv_id(eprint)
        if normalized:
            return normalized, "eprint"

    for field in ("arxiv", "url", "pdf", "doi"):
        normalized = normalize_arxiv_id(str(entry.get(field, "")).strip())
        if normalized:
            return normalized, field
    return None, None


def parse_file_field(field_value: str | None) -> tuple[str | None, str | None]:
    if not field_value:
        return None, None

    raw = field_value.strip()
    if not raw:
        return None, None

    for segment in (item.strip() for item in raw.split(";") if item.strip()):
        colon_wrapped = re.match(r"^:(.+):([A-Za-z0-9_+\-]+)$", segment)
        if colon_wrapped:
            return colon_wrapped.group(1).strip(), colon_wrapped.group(2).strip().lower()

        maybe_typed = re.match(r"^(.+):([A-Za-z0-9_+\-]+)$", segment)
        if maybe_typed:
            maybe_path = maybe_typed.group(1).strip()
            maybe_type = maybe_typed.group(2).strip().lower()
            if "/" in maybe_path or maybe_path.lower().endswith(".pdf"):
                return maybe_path, maybe_type

        if segment.lower().endswith(".pdf") or "/" in segment:
            return segment, "pdf"

    return None, None


def format_file_field(path: Path, file_type: str = "pdf") -> str:
    return f":{path.resolve()}:{file_type}"


def documents_subdir(entry_type_name: str) -> str:
    normalized = entry_type_name.strip().lower() or "misc"
    return TYPE_TO_DIR.get(normalized, "misc")


def documents_entry_dir(documents_root: Path, entry_type_name: str, key: str) -> Path:
    return documents_root / documents_subdir(entry_type_name) / key


def preferred_pdf_path(documents_root: Path, entry_type_name: str, key: str) -> Path:
    entry_dir = documents_entry_dir(documents_root, entry_type_name, key)
    return entry_dir / f"{key}.pdf"


def notes_dir(documents_root: Path, entry_type_name: str, key: str) -> Path:
    return documents_entry_dir(documents_root, entry_type_name, key) / "notes"


def notes_already_published(target_dir: Path) -> bool:
    return all((target_dir / filename).exists() for filename in PUBLISHED_ARTIFACTS)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def default_run_root(inputs: list[str], selector_label: str | None, runs_root: Path) -> Path:
    label_seed = selector_label or Path(inputs[0]).stem if inputs else "batch"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return runs_root / f"{stamp}-{slugify(label_seed)}"


def normalize_title(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("{", "").replace("}", "")
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def extract_openreview_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = OPENREVIEW_ID_RE.search(text)
    if match:
        return match.group(1)
    return None


def url_fingerprint(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if not k.lower().startswith("utm_")]
    normalized_query = "&".join(f"{k}={v}" for k, v in sorted(query))
    base = f"{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    if normalized_query:
        return f"{base}?{normalized_query}"
    return base


def split_source_bib_files(raw_value: str) -> list[Path]:
    items = [item.strip() for item in raw_value.split(";") if item.strip()]
    return [Path(item).expanduser().resolve() for item in items]


def canonical_bib_for_selector(selector_path: Path) -> Path | None:
    try:
        relative = selector_path.resolve().relative_to(ORALS_ROOT)
    except ValueError:
        return None
    canonical_path = CANONICAL_CONFERENCES_ROOT / relative
    if canonical_path.exists():
        return canonical_path.resolve()
    return None


def resolve_target_bib_file(source_bib_files: list[str]) -> str:
    candidates: set[Path] = set()
    for item in source_bib_files:
        source = Path(item).expanduser().resolve()
        canonical = canonical_bib_for_selector(source)
        if canonical is not None:
            candidates.add(canonical)
            continue
        candidates.add(source)
    if len(candidates) == 1:
        return str(next(iter(candidates)))
    return ""


def row_uses_oral_selector(row: dict[str, str], target_bib_file: Path) -> bool:
    for source in split_source_bib_files(row.get("source_bib_files", "")):
        canonical = canonical_bib_for_selector(source)
        if canonical is not None and canonical == target_bib_file.resolve():
            return True
    return False


def merge_entries(bib_paths: list[Path]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    merged: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    conflicted_keys: set[str] = set()

    for bib_path in bib_paths:
        db = parse_bib_file(bib_path)
        for entry in db.entries:
            key = entry_key(entry)
            if not key:
                skipped.append(
                    {
                        "job_id": "",
                        "key": "",
                        "entry_type": entry_type(entry) or "misc",
                        "title": str(entry.get("title", "")).strip(),
                        "year": str(entry.get("year", "")).strip(),
                        "selector_url": str(entry.get("url", "")).strip(),
                        "selector_pdf": str(entry.get("pdf", "")).strip(),
                        "arxiv_id": "",
                        "arxiv_url": "",
                        "workspace_dir": "",
                        "notes_dir": "",
                        "preferred_pdf_path": "",
                        "existing_pdf_path": "",
                        "source_bib_files": str(bib_path),
                        "target_bib_file": "",
                        "reason": "skip_missing_key",
                    }
                )
                continue

            if key in conflicted_keys:
                continue

            normalized_entry_type = entry_type(entry) or "misc"
            arxiv_id, arxiv_source = extract_arxiv_id(entry)
            file_path, _ = parse_file_field(str(entry.get("file", "")).strip())
            source_file = str(bib_path.resolve())

            existing = merged.get(key)
            if existing is None:
                merged[key] = {
                    "job_id": key,
                    "key": key,
                    "entry_type": normalized_entry_type,
                    "title": str(entry.get("title", "")).strip(),
                    "year": str(entry.get("year", "")).strip(),
                    "selector_url": str(entry.get("url", "")).strip(),
                    "selector_pdf": str(entry.get("pdf", "")).strip(),
                    "arxiv_id": arxiv_id or "",
                    "arxiv_source_field": arxiv_source or "",
                    "existing_pdf_path": file_path or "",
                    "source_bib_files": [source_file],
                }
                continue

            type_conflict = existing["entry_type"] != normalized_entry_type
            id_conflict = bool(existing["arxiv_id"] and arxiv_id and existing["arxiv_id"] != arxiv_id)
            if type_conflict or id_conflict:
                skipped.append(
                    {
                        "job_id": key,
                        "key": key,
                        "entry_type": normalized_entry_type,
                        "title": str(entry.get("title", "")).strip(),
                        "year": str(entry.get("year", "")).strip(),
                        "selector_url": str(entry.get("url", "")).strip(),
                        "selector_pdf": str(entry.get("pdf", "")).strip(),
                        "arxiv_id": arxiv_id or "",
                        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                        "workspace_dir": "",
                        "notes_dir": "",
                        "preferred_pdf_path": "",
                        "existing_pdf_path": file_path or "",
                        "source_bib_files": ";".join(sorted(set([*existing["source_bib_files"], source_file]))),
                        "target_bib_file": "",
                        "reason": "skip_conflicting_duplicate_key",
                    }
                )
                conflicted_keys.add(key)
                merged.pop(key, None)
                continue

            existing["source_bib_files"] = sorted(set([*existing["source_bib_files"], source_file]))
            if not existing["arxiv_id"] and arxiv_id:
                existing["arxiv_id"] = arxiv_id
                existing["arxiv_source_field"] = arxiv_source or ""
            if not existing["existing_pdf_path"] and file_path:
                existing["existing_pdf_path"] = file_path
            if not existing["title"]:
                existing["title"] = str(entry.get("title", "")).strip()
            if not existing["year"]:
                existing["year"] = str(entry.get("year", "")).strip()
            if not existing["selector_url"]:
                existing["selector_url"] = str(entry.get("url", "")).strip()
            if not existing["selector_pdf"]:
                existing["selector_pdf"] = str(entry.get("pdf", "")).strip()

    return merged, skipped


def build_plan(
    bib_inputs: list[str],
    run_root: Path,
    documents_root: Path,
    force: bool,
) -> dict[str, Any]:
    bib_paths = resolve_bib_paths(bib_inputs)
    if not bib_paths:
        raise SystemExit("no BibTeX files resolved from the provided inputs")

    merged, skipped = merge_entries(bib_paths)
    ready_jobs: list[dict[str, Any]] = []
    skipped_jobs: list[dict[str, Any]] = list(skipped)
    workspace_root = run_root / "workspaces"

    for key in sorted(merged):
        item = merged[key]
        target_notes_dir = notes_dir(documents_root, item["entry_type"], key)
        target_pdf_path = preferred_pdf_path(documents_root, item["entry_type"], key)
        workspace_slug = item["arxiv_id"] or key
        job = {
            "job_id": item["job_id"],
            "key": key,
            "entry_type": item["entry_type"],
            "title": item["title"],
            "year": item["year"],
            "selector_url": item["selector_url"],
            "selector_pdf": item["selector_pdf"],
            "arxiv_id": item["arxiv_id"],
            "arxiv_url": f"https://arxiv.org/abs/{item['arxiv_id']}" if item["arxiv_id"] else "",
            "workspace_dir": str((workspace_root / workspace_slug).resolve()),
            "notes_dir": str(target_notes_dir.resolve()),
            "preferred_pdf_path": str(target_pdf_path.resolve()),
            "existing_pdf_path": item["existing_pdf_path"],
            "source_bib_files": ";".join(item["source_bib_files"]),
            "target_bib_file": resolve_target_bib_file(item["source_bib_files"]),
        }

        if notes_already_published(target_notes_dir) and not force:
            skipped_jobs.append({**job, "reason": "skip_existing_notes"})
            continue
        if not item["arxiv_id"]:
            skipped_jobs.append({**job, "reason": "skip_missing_arxiv"})
            continue
        ready_jobs.append(job)

    plan = {
        "inputs": [str(path) for path in bib_paths],
        "run_root": str(run_root.resolve()),
        "documents_root": str(documents_root.resolve()),
        "workspace_root": str(workspace_root.resolve()),
        "ready_count": len(ready_jobs),
        "skipped_count": len(skipped_jobs),
        "ready_jobs": ready_jobs,
        "skipped_jobs": skipped_jobs,
        "ready_reasons": sorted({row.get("reason", "ready") for row in ready_jobs if row.get("reason")}),
        "skip_reasons": sorted({row["reason"] for row in skipped_jobs}),
    }
    return plan


def write_plan_outputs(plan: dict[str, Any], run_root: Path) -> dict[str, str]:
    run_root.mkdir(parents=True, exist_ok=True)
    plan_path = run_root / "batch-plan.json"
    summary_path = run_root / "summary.json"
    jobs_csv_path = run_root / "jobs.csv"
    skipped_csv_path = run_root / "skipped.csv"

    summary = {
        "run_root": plan["run_root"],
        "documents_root": plan["documents_root"],
        "workspace_root": plan["workspace_root"],
        "inputs": plan["inputs"],
        "ready_count": plan["ready_count"],
        "skipped_count": plan["skipped_count"],
        "skip_reasons": plan["skip_reasons"],
    }

    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(jobs_csv_path, plan["ready_jobs"], READY_FIELDS)
    write_csv(skipped_csv_path, plan["skipped_jobs"], SKIP_FIELDS)

    return {
        "plan_json": str(plan_path),
        "summary_json": str(summary_path),
        "jobs_csv": str(jobs_csv_path),
        "skipped_csv": str(skipped_csv_path),
    }


def publish_workspace(workspace: Path, notes_target_dir: Path, fail_if_exists: bool) -> dict[str, Any]:
    workspace = workspace.resolve()
    notes_target_dir = notes_target_dir.resolve()

    missing_sources = []
    copies: list[dict[str, str]] = []
    for published_name, (subdir, relative_name) in PUBLISHED_ARTIFACTS.items():
        source = workspace / subdir / relative_name
        target = notes_target_dir / published_name
        if not source.exists():
            missing_sources.append(str(source))
            continue
        copies.append({"source": str(source), "target": str(target)})

    if missing_sources:
        return {
            "status": "failed",
            "published": False,
            "workspace": str(workspace),
            "notes_dir": str(notes_target_dir),
            "missing_sources": missing_sources,
            "copied": [],
            "error": "missing required note artifacts in workspace",
        }

    semantic_audit = workspace_note_bundle_audit(workspace)
    if not semantic_audit["passed"]:
        return {
            "status": "failed",
            "published": False,
            "workspace": str(workspace),
            "notes_dir": str(notes_target_dir),
            "missing_sources": [],
            "copied": [],
            "error": "note bundle failed semantic audit",
            "semantic_errors": semantic_audit["errors"],
        }

    notes_target_dir.mkdir(parents=True, exist_ok=True)
    copied_targets: list[str] = []
    for item in copies:
        target = Path(item["target"])
        if fail_if_exists and target.exists():
            return {
                "status": "failed",
                "published": False,
                "workspace": str(workspace),
                "notes_dir": str(notes_target_dir),
                "missing_sources": [],
                "copied": copied_targets,
                "error": f"target already exists: {target}",
            }
        shutil.copy2(item["source"], item["target"])
        copied_targets.append(item["target"])

    return {
        "status": "published",
        "published": True,
        "workspace": str(workspace),
        "notes_dir": str(notes_target_dir),
        "missing_sources": [],
        "copied": copied_targets,
        "published_artifacts": sorted(PUBLISHED_ARTIFACTS),
    }


def load_results_rows(results_csv: Path) -> list[dict[str, str]]:
    with results_csv.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def workspace_pdf_path(workspace: Path) -> Path | None:
    pdf_dir = workspace / "artifacts" / "arxiv" / "pdf"
    if not pdf_dir.exists():
        return None
    candidates = sorted(pdf_dir.glob("*.pdf"))
    if not candidates:
        return None
    return candidates[0].resolve()


def worker_result_payload(row: dict[str, str]) -> dict[str, Any]:
    raw = row.get("result_json", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def normalized_published_artifacts(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {Path(str(item)).name for item in value if str(item).strip()}


def worker_result_publish_success(payload: dict[str, Any]) -> tuple[bool, str]:
    status = str(payload.get("status", "")).strip().lower()
    published = payload.get("published")
    if published is True or status in SUCCESSFUL_WORKER_STATUSES:
        artifacts = normalized_published_artifacts(payload.get("published_artifacts"))
        if artifacts and not set(PUBLISHED_ARTIFACTS).issubset(artifacts):
            missing = sorted(set(PUBLISHED_ARTIFACTS) - artifacts)
            return False, f"worker publish result omitted artifacts: {', '.join(missing)}"
        if nonempty_string(payload.get("error")):
            return False, str(payload.get("error")).strip()
        return True, ""
    return False, str(payload.get("error", "")).strip() or "worker did not report publish success"


def find_target_entry(entries: list[dict[str, Any]], row: dict[str, str]) -> tuple[dict[str, Any] | None, str, str]:
    key = row.get("key", "").strip()
    if key:
        for entry in entries:
            if entry_key(entry) == key:
                return entry, "key", ""

    row_arxiv_id = row.get("arxiv_id", "").strip()
    if row_arxiv_id:
        arxiv_matches = [entry for entry in entries if extract_arxiv_id(entry)[0] == row_arxiv_id]
        if len(arxiv_matches) == 1:
            return arxiv_matches[0], "arxiv", ""
        if len(arxiv_matches) > 1:
            return None, "", "ambiguous_arxiv_match"

    row_title = normalize_title(row.get("title", ""))
    if row_title:
        title_matches = [entry for entry in entries if normalize_title(str(entry.get("title", ""))) == row_title]
        if len(title_matches) == 1:
            return title_matches[0], "title", ""
        if len(title_matches) > 1:
            return None, "", "ambiguous_title_match"

    openreview_ids = {
        candidate
        for candidate in (
            extract_openreview_id(row.get("selector_url")),
            extract_openreview_id(row.get("selector_pdf")),
        )
        if candidate
    }
    if openreview_ids:
        openreview_matches = [
            entry
            for entry in entries
            if extract_openreview_id(str(entry.get("url", ""))) in openreview_ids
            or extract_openreview_id(str(entry.get("pdf", ""))) in openreview_ids
        ]
        deduped = {entry_key(entry): entry for entry in openreview_matches if entry_key(entry)}
        if len(deduped) == 1:
            return next(iter(deduped.values())), "openreview", ""
        if len(deduped) > 1:
            return None, "", "ambiguous_openreview_match"

    selector_links = {
        candidate
        for candidate in (
            url_fingerprint(row.get("selector_url")),
            url_fingerprint(row.get("selector_pdf")),
        )
        if candidate
    }
    if selector_links:
        link_matches = []
        for entry in entries:
            entry_links = {
                candidate
                for candidate in (
                    url_fingerprint(str(entry.get("url", ""))),
                    url_fingerprint(str(entry.get("pdf", ""))),
                )
                if candidate
            }
            if selector_links & entry_links:
                link_matches.append(entry)
        deduped = {entry_key(entry): entry for entry in link_matches if entry_key(entry)}
        if len(deduped) == 1:
            return next(iter(deduped.values())), "link", ""
        if len(deduped) > 1:
            return None, "", "ambiguous_link_match"

    return None, "", "target_entry_not_found"


def materialize_preferred_pdf(row: dict[str, str], entry: dict[str, Any]) -> dict[str, str]:
    target_path = Path(row["preferred_pdf_path"]).expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        return {"status": "ok", "action": "already_preferred", "source_path": str(target_path)}

    entry_file_path, _ = parse_file_field(str(entry.get("file", "")).strip())
    existing_candidates: list[tuple[Path, str, bool]] = []
    if entry_file_path:
        existing_candidates.append((Path(entry_file_path).expanduser().resolve(), "moved_entry_file", True))
    row_existing = row.get("existing_pdf_path", "").strip()
    if row_existing:
        existing_candidates.append((Path(row_existing).expanduser().resolve(), "moved_existing_file", True))

    seen_sources: set[Path] = set()
    for source_path, action, do_move in existing_candidates:
        if source_path in seen_sources:
            continue
        seen_sources.add(source_path)
        if source_path == target_path:
            continue
        if not source_path.exists():
            continue
        shutil.move(str(source_path), str(target_path))
        return {"status": "ok", "action": action, "source_path": str(source_path)}

    workspace = Path(row.get("workspace_dir", "")).expanduser().resolve()
    workspace_pdf = workspace_pdf_path(workspace)
    if workspace_pdf is not None:
        shutil.copy2(workspace_pdf, target_path)
        return {"status": "ok", "action": "copied_workspace_pdf", "source_path": str(workspace_pdf)}

    return {"status": "error", "action": "missing_pdf_source", "error": "no local or workspace PDF available"}


def finalize_results(results_csv: Path, report_json: Path | None = None) -> dict[str, Any]:
    rows = load_results_rows(results_csv)
    per_row_reports: list[dict[str, str]] = []
    rows_by_target: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        report = {
            "key": row.get("key", "").strip(),
            "target_bib_file": row.get("target_bib_file", "").strip(),
            "matched_entry_key": "",
            "match_mode": "",
            "notes_dir": row.get("notes_dir", "").strip(),
            "preferred_pdf_path": row.get("preferred_pdf_path", "").strip(),
            "pdf_action": "",
            "bib_action": "",
            "status": "",
            "error": "",
        }

        if row.get("status", "").strip() != "completed":
            report["status"] = "skipped_worker_incomplete"
            report["error"] = row.get("last_error", "").strip()
            per_row_reports.append(report)
            continue

        result_payload = worker_result_payload(row)
        if result_payload:
            success, error = worker_result_publish_success(result_payload)
        else:
            success, error = True, ""
        if not success:
            report["status"] = "skipped_worker_result"
            report["error"] = error
            per_row_reports.append(report)
            continue

        target_bib_file = report["target_bib_file"]
        if not target_bib_file:
            report["status"] = "skipped_missing_target_bib"
            report["error"] = "planner could not resolve a single canonical bibliography file"
            per_row_reports.append(report)
            continue

        rows_by_target.setdefault(target_bib_file, []).append(row)
        per_row_reports.append(report)

    reports_by_key = {f"{item['target_bib_file']}::{item['key']}": item for item in per_row_reports}
    target_write_reports: list[dict[str, str]] = []

    for target_bib_file, target_rows in sorted(rows_by_target.items()):
        target_path = Path(target_bib_file).expanduser().resolve()
        if not target_path.exists():
            for row in target_rows:
                report = reports_by_key[f"{target_bib_file}::{row.get('key', '').strip()}"]
                report["status"] = "missing_target_bib"
                report["error"] = f"target bibliography file does not exist: {target_path}"
            continue

        db = parse_bib_file(target_path)
        baseline_entries = len(db.entries)
        baseline_comments = len(db.comments)
        modified = False

        for row in target_rows:
            report = reports_by_key[f"{target_bib_file}::{row.get('key', '').strip()}"]
            notes_audit = published_note_bundle_audit(Path(row.get("notes_dir", "")).expanduser().resolve())
            if not notes_audit["passed"]:
                report["status"] = "notes_audit_failed"
                report["error"] = "; ".join(notes_audit["errors"])
                continue
            entry, match_mode, error = find_target_entry(db.entries, row)
            if entry is None:
                if error == "target_entry_not_found" and row_uses_oral_selector(row, target_path):
                    report["status"] = "canonical_entry_missing"
                    report["error"] = f"selector entry not present in canonical target: {target_path}"
                else:
                    report["status"] = "target_entry_unresolved"
                    report["error"] = error
                continue

            report["matched_entry_key"] = entry_key(entry)
            report["match_mode"] = match_mode

            pdf_result = materialize_preferred_pdf(row, entry)
            report["pdf_action"] = pdf_result.get("action", "")
            if pdf_result.get("status") != "ok":
                report["status"] = "pdf_unavailable"
                report["error"] = pdf_result.get("error", "")
                continue

            normalized_file_field = format_file_field(Path(row["preferred_pdf_path"]).expanduser().resolve(), "pdf")
            if str(entry.get("file", "")).strip() != normalized_file_field:
                entry["file"] = normalized_file_field
                report["bib_action"] = "updated_file_field"
                modified = True
            else:
                report["bib_action"] = "file_field_already_current"
            report["status"] = "finalized"

        if modified:
            transactional_write_bib_file(
                target_path,
                db,
                baseline_entries=baseline_entries,
                baseline_comments=baseline_comments,
            )
            target_write_reports.append({"target_bib_file": str(target_path), "status": "written"})
        else:
            target_write_reports.append({"target_bib_file": str(target_path), "status": "unchanged"})

    summary = {
        "results_csv": str(results_csv.resolve()),
        "report_json": str((report_json or results_csv.parent / "finalize-report.json").resolve()),
        "report_csv": str((results_csv.parent / "finalize-results.csv").resolve()),
        "rows_total": len(rows),
        "finalized_count": sum(1 for row in per_row_reports if row["status"] == "finalized"),
        "skipped_count": sum(1 for row in per_row_reports if row["status"].startswith("skipped_")),
        "error_count": sum(1 for row in per_row_reports if row["status"] not in {"finalized"} and not row["status"].startswith("skipped_")),
        "target_files": target_write_reports,
        "rows": per_row_reports,
    }

    final_report_json = report_json or results_csv.parent / "finalize-report.json"
    final_report_csv = results_csv.parent / "finalize-results.csv"
    final_report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(final_report_csv, per_row_reports, FINALIZE_FIELDS)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, publish, and finalize batch research-paper-notes runs from bibliography selections.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    plan_parser = subcommands.add_parser("plan")
    plan_parser.add_argument("inputs", nargs="+", help="BibTeX files or globs to scan")
    plan_parser.add_argument("--run-root", help="Directory for plan outputs and temporary workspaces")
    plan_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT), help="Base directory used when --run-root is omitted")
    plan_parser.add_argument("--documents-root", default=str(DEFAULT_DOCUMENTS_ROOT))
    plan_parser.add_argument("--selector-label", default=None, help="Optional label used when synthesizing a run directory")
    plan_parser.add_argument("--force", action="store_true", help="Include jobs even when notes are already published")
    plan_parser.add_argument("--json", action="store_true", help="Emit the summary JSON to stdout")

    publish_parser = subcommands.add_parser("publish")
    publish_parser.add_argument("--workspace", required=True, help="Completed research-paper-notes workspace")
    publish_parser.add_argument("--notes-dir", required=True, help="Durable notes destination directory")
    publish_parser.add_argument("--fail-if-exists", action="store_true")
    publish_parser.add_argument("--json", action="store_true", help="Emit publish report JSON to stdout")

    finalize_parser = subcommands.add_parser("finalize")
    finalize_parser.add_argument("--results-csv", required=True, help="CSV exported by spawn_agents_on_csv")
    finalize_parser.add_argument("--report-json", help="Optional explicit finalize report path")
    finalize_parser.add_argument("--json", action="store_true", help="Emit finalize summary JSON to stdout")

    args = parser.parse_args()

    if args.command == "plan":
        runs_root = Path(args.runs_root).expanduser().resolve()
        run_root = Path(args.run_root).expanduser().resolve() if args.run_root else default_run_root(args.inputs, args.selector_label, runs_root).resolve()
        documents_root = Path(args.documents_root).expanduser().resolve()
        plan = build_plan(args.inputs, run_root, documents_root, force=args.force)
        outputs = write_plan_outputs(plan, run_root)
        summary = {
            "run_root": plan["run_root"],
            "documents_root": plan["documents_root"],
            "workspace_root": plan["workspace_root"],
            "ready_count": plan["ready_count"],
            "skipped_count": plan["skipped_count"],
            "skip_reasons": plan["skip_reasons"],
            "outputs": outputs,
        }
        if args.json:
            emit_json(summary)
        return 0

    if args.command == "publish":
        report = publish_workspace(
            Path(args.workspace).expanduser(),
            Path(args.notes_dir).expanduser(),
            fail_if_exists=args.fail_if_exists,
        )
        if args.json:
            emit_json(report)
        return 0 if report.get("published") else 2

    summary = finalize_results(
        Path(args.results_csv).expanduser().resolve(),
        report_json=Path(args.report_json).expanduser().resolve() if args.report_json else None,
    )
    if args.json:
        emit_json(summary)
    return 0 if summary["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
