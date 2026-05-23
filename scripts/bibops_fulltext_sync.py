#!/usr/bin/env python3
"""GROBID full-text extraction for locally cached BibTeX PDFs."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests

try:
    from bibops_pdf_sync import (
        DEFAULT_BASE_DIR,
        get_document_dir,
        get_target_path,
        parse_file_field,
        verify_pdf,
    )
    from core.bibtex_io import parse_bib_file, resolve_bib_paths
except ModuleNotFoundError:  # pragma: no cover - package import path
    from .bibops_pdf_sync import (
        DEFAULT_BASE_DIR,
        get_document_dir,
        get_target_path,
        parse_file_field,
        verify_pdf,
    )
    from .core.bibtex_io import parse_bib_file, resolve_bib_paths

GROBID_CONFIG_VERSION = 1
DEFAULT_GROBID_URL = "http://localhost:8070"
DEFAULT_ENDPOINT = "/api/processFulltextDocument"
DEFAULT_TEI_COORDINATES = ("figure", "formula", "ref", "biblStruct")
PAGE_TIER_ORDER = ("article", "unknown", "medium", "long", "huge")
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
_THREAD_LOCAL = threading.local()


@dataclasses.dataclass
class FulltextSyncOptions:
    targets: list[str]
    base_dir: Path = DEFAULT_BASE_DIR
    grobid_url: str = DEFAULT_GROBID_URL
    max_entries: int = 0
    workers: int = 0
    medium_workers: int = 0
    long_workers: int = 0
    huge_workers: int = 0
    force: bool = False
    dry_run: bool = False
    generate_ids: bool = False
    consolidate_header: bool = True
    consolidate_citations: bool = False
    consolidate_funders: bool = False
    include_raw_citations: bool = True
    include_raw_affiliations: bool = False
    include_raw_copyrights: bool = False
    segment_sentences: bool = True
    tei_coordinates: bool = True
    tei_coordinate_elements: tuple[str, ...] = DEFAULT_TEI_COORDINATES
    timeout_connect_seconds: float = 10.0
    timeout_read_seconds: float = 1200.0
    medium_timeout_read_seconds: float = 1200.0
    long_timeout_read_seconds: float = 3600.0
    huge_timeout_read_seconds: float = 7200.0
    medium_page_threshold: int = 50
    long_page_threshold: int = 150
    huge_page_threshold: int = 500
    pdfinfo_timeout_seconds: float = 15.0
    dispatch_batch_size: int = 256
    grobid_max_attempts: int = 3
    grobid_busy_sleep_seconds: float = 5.0
    progress_log: Path | None = None
    console_progress: bool = False


@dataclasses.dataclass(frozen=True)
class FulltextTierPlan:
    workers: int
    timeout_read_seconds: float


@dataclasses.dataclass
class FulltextWorkItem:
    bib_file: Path
    entry_key: str
    entry_type: str
    title: str
    author: str
    pdf_path: Path
    document_dir: Path
    tei_path: Path
    provenance_path: Path
    page_count: int | None = None
    page_tier: str = "unknown"
    pdf_sha: str | None = None
    pdf_size: int = 0
    pdf_mtime_ns: int = 0


@dataclasses.dataclass
class FulltextOutcome:
    bib_file: str
    key: str
    status: str
    message: str
    pdf_path: str | None = None
    tei_path: str | None = None
    elapsed_seconds: float = 0.0
    tei_bytes: int = 0
    page_count: int | None = None
    page_tier: str = "unknown"


@dataclasses.dataclass
class FulltextSyncResult:
    summary: dict[str, int | float | str]
    failures: list[FulltextOutcome]


class ProgressLogger:
    def __init__(self, path: Path | None, *, console_progress: bool = False) -> None:
        self.path = path
        self.console_progress = console_progress
        self._lock = threading.Lock()
        self._handle = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None

    def emit(self, payload: dict[str, Any]) -> None:
        payload = {"timestamp": now_iso(), **payload}
        with self._lock:
            if self._handle:
                self._handle.write(json.dumps(payload, sort_keys=True) + "\n")
                self._handle.flush()
            if self.console_progress:
                parts = [
                    str(payload.get("status", "")),
                    str(payload.get("bib_file", "")),
                    str(payload.get("key", "")),
                    str(payload.get("message", "")),
                ]
                print(" | ".join(p for p in parts if p), flush=True)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def normalize_text(value: str) -> str:
    value = (value or "").replace("{", "").replace("}", "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def title_similarity(left: str, right: str) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def first_author_surname(author_field: str) -> str:
    first = (author_field or "").split(" and ", 1)[0].strip()
    if "," in first:
        first = first.split(",", 1)[0].strip()
    tokens = normalize_text(first).split()
    return tokens[-1] if tokens else ""


def grobid_http_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _THREAD_LOCAL.session = session
    return session


def grobid_parameters(options: FulltextSyncOptions | None = None) -> list[tuple[str, str]]:
    if options is None:
        options = FulltextSyncOptions(targets=[])
    params: list[tuple[str, str]] = []
    if options.generate_ids:
        params.append(("generateIDs", "1"))
    if options.consolidate_header:
        params.append(("consolidateHeader", "1"))
    if options.consolidate_citations:
        params.append(("consolidateCitations", "1"))
    if options.consolidate_funders:
        params.append(("consolidateFunders", "1"))
    if options.include_raw_citations:
        params.append(("includeRawCitations", "1"))
    if options.include_raw_affiliations:
        params.append(("includeRawAffiliations", "1"))
    if options.include_raw_copyrights:
        params.append(("includeRawCopyrights", "1"))
    if options.segment_sentences:
        params.append(("segmentSentences", "1"))
    if options.tei_coordinates:
        params.extend(("teiCoordinates", name) for name in options.tei_coordinate_elements)
    return params


def extraction_config_sha256(parameters: list[tuple[str, str]]) -> str:
    payload = {
        "schema_version": GROBID_CONFIG_VERSION,
        "endpoint": DEFAULT_ENDPOINT,
        "parameters": parameters,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def parameter_counter(parameters: Any) -> Counter[tuple[str, str]]:
    out: Counter[tuple[str, str]] = Counter()
    if not isinstance(parameters, list):
        return out
    for item in parameters:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out[(str(item[0]), str(item[1]))] += 1
    return out


def extraction_parameters_compatible(stored_parameters: Any, requested_parameters: list[tuple[str, str]]) -> bool:
    stored = parameter_counter(stored_parameters)
    requested = parameter_counter(requested_parameters)
    if not requested:
        return True
    return all(stored.get(param, 0) >= count for param, count in requested.items())


def normalize_page_thresholds(options: FulltextSyncOptions) -> tuple[int, int, int]:
    medium = max(1, int(options.medium_page_threshold))
    long = max(medium + 1, int(options.long_page_threshold))
    huge = max(long + 1, int(options.huge_page_threshold))
    return medium, long, huge


def classify_page_tier(page_count: int | None, options: FulltextSyncOptions) -> str:
    if page_count is None or page_count <= 0:
        return "unknown"
    medium_threshold, long_threshold, huge_threshold = normalize_page_thresholds(options)
    if page_count > huge_threshold:
        return "huge"
    if page_count > long_threshold:
        return "long"
    if page_count > medium_threshold:
        return "medium"
    return "article"


def pdf_page_count(path: Path, *, timeout_seconds: float = 15.0) -> int | None:
    try:
        proc = subprocess.run(
            ["pdfinfo", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=max(1.0, timeout_seconds),
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            raw_value = line.split(":", 1)[1].strip().split()[0:1]
            if not raw_value:
                return None
            try:
                pages = int(raw_value[0])
            except ValueError:
                return None
            return pages if pages > 0 else None
    return None


def auto_worker_counts(cpu_threads: int | None = None) -> dict[str, int]:
    threads = max(1, int(cpu_threads or os.cpu_count() or 1))
    if threads <= 2:
        article = 1
    else:
        article = max(2, min(8, threads // 2))
    medium = max(1, min(4, article // 2))
    long = max(1, min(2, threads // 12))
    return {
        "article": article,
        "unknown": medium,
        "medium": medium,
        "long": long,
        "huge": 1,
    }


def effective_tier_plan(options: FulltextSyncOptions, *, cpu_threads: int | None = None) -> dict[str, FulltextTierPlan]:
    auto = auto_worker_counts(cpu_threads)

    def workers(raw_value: int, tier: str) -> int:
        value = int(raw_value)
        return max(1, value) if value > 0 else auto[tier]

    article_workers = workers(options.workers, "article")
    medium_workers = workers(options.medium_workers, "medium")
    long_workers = workers(options.long_workers, "long")
    huge_workers = workers(options.huge_workers, "huge")
    article_timeout = max(1.0, float(options.timeout_read_seconds))
    medium_timeout = max(article_timeout, float(options.medium_timeout_read_seconds))
    long_timeout = max(medium_timeout, float(options.long_timeout_read_seconds))
    huge_timeout = max(long_timeout, float(options.huge_timeout_read_seconds))
    return {
        "article": FulltextTierPlan(article_workers, article_timeout),
        "unknown": FulltextTierPlan(medium_workers, medium_timeout),
        "medium": FulltextTierPlan(medium_workers, medium_timeout),
        "long": FulltextTierPlan(long_workers, long_timeout),
        "huge": FulltextTierPlan(huge_workers, huge_timeout),
    }


def grobid_version(base_url: str, timeout: tuple[float, float]) -> dict[str, str]:
    url = urljoin(base_url.rstrip("/") + "/", "api/version")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return {
        "version": str(payload.get("version", "")).strip(),
        "revision": str(payload.get("revision", "")).strip(),
    }


def tei_text(root: ET.Element, xpath: str) -> str:
    node = root.find(xpath, TEI_NS)
    if node is None:
        return ""
    return " ".join(t.strip() for t in node.itertext() if t.strip())


def tei_all_text(root: ET.Element, xpath: str) -> str:
    chunks: list[str] = []
    for node in root.findall(xpath, TEI_NS):
        chunks.extend(t.strip() for t in node.itertext() if t.strip())
    return " ".join(chunks)


def tei_features(tei: str, *, bib_title: str, bib_author: str) -> dict[str, Any]:
    root = ET.fromstring(tei)
    title = tei_text(root, ".//tei:fileDesc/tei:titleStmt/tei:title")
    abstract = tei_all_text(root, ".//tei:profileDesc/tei:abstract")
    body = tei_all_text(root, ".//tei:text/tei:body")
    references = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    first_surname = tei_text(root, ".//tei:sourceDesc//tei:analytic/tei:author[1]//tei:surname")
    if not first_surname:
        first_surname = tei_text(root, ".//tei:fileDesc//tei:author[1]//tei:surname")
    bib_surname = first_author_surname(bib_author)
    extracted_surname = normalize_text(first_surname).split()
    extracted_surname_value = extracted_surname[-1] if extracted_surname else ""
    return {
        "title": title,
        "has_title": bool(title.strip()),
        "has_abstract": bool(abstract.strip()),
        "body_text_chars": len(body),
        "reference_count": len(references),
        "title_similarity": round(title_similarity(bib_title, title), 4),
        "first_author_surname": extracted_surname_value,
        "bib_first_author_surname": bib_surname,
        "first_author_match": bool(bib_surname and extracted_surname_value and bib_surname == extracted_surname_value),
    }


def metadata_is_current(
    provenance_path: Path,
    tei_path: Path,
    *,
    pdf_sha: str,
    grobid_info: dict[str, str],
    config_sha: str,
    parameters: list[tuple[str, str]] | None = None,
) -> bool:
    if not provenance_path.exists() or not tei_path.exists():
        return False
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if (
        payload.get("status") != "ok"
        or payload.get("pdf", {}).get("sha256") != pdf_sha
        or payload.get("grobid", {}).get("version") != grobid_info.get("version")
        or payload.get("grobid", {}).get("revision") != grobid_info.get("revision")
    ):
        return False
    grobid_payload = payload.get("grobid", {})
    if grobid_payload.get("extraction_config_sha256") == config_sha:
        return True
    return bool(parameters and extraction_parameters_compatible(grobid_payload.get("parameters"), parameters))


def load_provenance(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def provenance_has_current_extraction(
    payload: dict[str, Any] | None,
    tei_path: Path,
    *,
    grobid_info: dict[str, str],
    config_sha: str,
    parameters: list[tuple[str, str]] | None = None,
) -> bool:
    if payload is None or not tei_path.exists():
        return False
    if (
        payload.get("status") != "ok"
        or payload.get("grobid", {}).get("version") != grobid_info.get("version")
        or payload.get("grobid", {}).get("revision") != grobid_info.get("revision")
    ):
        return False
    grobid_payload = payload.get("grobid", {})
    if grobid_payload.get("extraction_config_sha256") == config_sha:
        return True
    return bool(parameters and extraction_parameters_compatible(grobid_payload.get("parameters"), parameters))


def provenance_pdf_matches_stat(payload: dict[str, Any] | None, *, pdf_size: int, pdf_mtime_ns: int) -> bool:
    if payload is None:
        return False
    pdf_payload = payload.get("pdf", {})
    if not isinstance(pdf_payload, dict):
        return False
    return pdf_payload.get("bytes") == pdf_size and pdf_payload.get("mtime_ns") == pdf_mtime_ns


def provenance_cached_pages(
    payload: dict[str, Any] | None,
    *,
    pdf_sha: str | None,
    pdf_size: int,
    pdf_mtime_ns: int,
) -> int | None:
    if payload is None:
        return None
    pdf_payload = payload.get("pdf", {})
    if not isinstance(pdf_payload, dict):
        return None

    matches_pdf = False
    if pdf_sha and pdf_payload.get("sha256") == pdf_sha:
        matches_pdf = True
    elif provenance_pdf_matches_stat(payload, pdf_size=pdf_size, pdf_mtime_ns=pdf_mtime_ns):
        matches_pdf = True
    if not matches_pdf:
        return None

    pages = pdf_payload.get("pages")
    if isinstance(pages, int) and pages > 0:
        return pages
    return None


def canonical_item_for_entry(bib_file: Path, entry: dict[str, Any], base_dir: Path) -> FulltextWorkItem:
    key = str(entry.get("ID", "")).strip()
    entry_type = str(entry.get("ENTRYTYPE", "misc")).strip().lower() or "misc"
    document_dir = get_document_dir(entry, base_dir)
    pdf_path = get_target_path(entry, base_dir)
    return FulltextWorkItem(
        bib_file=bib_file,
        entry_key=key,
        entry_type=entry_type,
        title=str(entry.get("title", "")).strip(),
        author=str(entry.get("author", "")).strip(),
        pdf_path=pdf_path,
        document_dir=document_dir,
        tei_path=document_dir / f"{key}.tei.xml",
        provenance_path=document_dir / f"{key}.grobid.json",
    )


def scan_work(
    options: FulltextSyncOptions,
) -> tuple[list[FulltextWorkItem], list[FulltextOutcome], dict[str, int | float | str]]:
    files = resolve_bib_paths(options.targets)
    summary: dict[str, int | float | str] = {
        "files_total": len(files),
        "entries_total": 0,
        "entries_considered": 0,
        "work_items": 0,
        "article_items": 0,
        "unknown_page_items": 0,
        "medium_items": 0,
        "long_items": 0,
        "huge_items": 0,
        "missing_file_field": 0,
        "noncanonical_file_field": 0,
        "invalid_pdf": 0,
        "parse_errors": 0,
        "unresolved_targets": 0,
    }
    work: list[FulltextWorkItem] = []
    preflight: list[FulltextOutcome] = []

    for bib_file in files:
        try:
            db = parse_bib_file(bib_file)
        except Exception as exc:
            summary["parse_errors"] = int(summary["parse_errors"]) + 1
            preflight.append(FulltextOutcome(str(bib_file), "*", "parse_error", str(exc)))
            continue

        for idx, entry in enumerate(db.entries, start=1):
            if options.max_entries and idx > options.max_entries:
                break
            summary["entries_total"] = int(summary["entries_total"]) + 1
            summary["entries_considered"] = int(summary["entries_considered"]) + 1
            key = str(entry.get("ID", "")).strip()
            raw_file = str(entry.get("file", "")).strip()
            if not raw_file:
                summary["missing_file_field"] = int(summary["missing_file_field"]) + 1
                preflight.append(FulltextOutcome(str(bib_file), key, "missing_file_field", "entry has no local PDF file field"))
                continue

            parsed_path, _kind = parse_file_field(raw_file)
            if not parsed_path:
                summary["missing_file_field"] = int(summary["missing_file_field"]) + 1
                preflight.append(FulltextOutcome(str(bib_file), key, "missing_file_field", "file field has no parseable PDF path"))
                continue

            item = canonical_item_for_entry(bib_file, entry, options.base_dir)
            current_pdf = Path(parsed_path).expanduser()
            if not current_pdf.is_absolute():
                current_pdf = (bib_file.parent / current_pdf).resolve()
            if current_pdf.resolve() != item.pdf_path.resolve():
                summary["noncanonical_file_field"] = int(summary["noncanonical_file_field"]) + 1
                preflight.append(
                    FulltextOutcome(
                        str(bib_file),
                        key,
                        "noncanonical_file_field",
                        f"expected {item.pdf_path}, got {current_pdf}",
                        pdf_path=str(current_pdf),
                        tei_path=str(item.tei_path),
                    )
                )
                continue

            ok, reason = verify_pdf(item.pdf_path)
            if not ok:
                summary["invalid_pdf"] = int(summary["invalid_pdf"]) + 1
                preflight.append(
                    FulltextOutcome(str(bib_file), key, "invalid_pdf", reason, pdf_path=str(item.pdf_path))
                )
                continue

            work.append(item)

    summary["work_items"] = len(work)
    return work, preflight, summary


def outcome_for_skipped_current(item: FulltextWorkItem) -> FulltextOutcome:
    return FulltextOutcome(
        bib_file=str(item.bib_file),
        key=item.entry_key,
        status="skipped_current",
        message="TEI already current for PDF identity and GROBID config",
        pdf_path=str(item.pdf_path),
        tei_path=str(item.tei_path),
        page_count=item.page_count,
        page_tier=item.page_tier,
    )


def prepare_item(
    item: FulltextWorkItem,
    *,
    options: FulltextSyncOptions,
    grobid_info: dict[str, str],
    config_sha: str,
    parameters: list[tuple[str, str]],
) -> tuple[FulltextWorkItem | None, FulltextOutcome | None]:
    stat = item.pdf_path.stat()
    pdf_size = stat.st_size
    pdf_mtime_ns = stat.st_mtime_ns
    provenance = load_provenance(item.provenance_path)
    has_current_extraction = provenance_has_current_extraction(
        provenance,
        item.tei_path,
        grobid_info=grobid_info,
        config_sha=config_sha,
        parameters=parameters,
    )

    cached_pages = provenance_cached_pages(
        provenance,
        pdf_sha=None,
        pdf_size=pdf_size,
        pdf_mtime_ns=pdf_mtime_ns,
    )

    if not options.force and has_current_extraction and provenance_pdf_matches_stat(
        provenance,
        pdf_size=pdf_size,
        pdf_mtime_ns=pdf_mtime_ns,
    ):
        page_tier = classify_page_tier(cached_pages, options)
        skipped_item = dataclasses.replace(
            item,
            page_count=cached_pages,
            page_tier=page_tier,
            pdf_size=pdf_size,
            pdf_mtime_ns=pdf_mtime_ns,
        )
        return None, outcome_for_skipped_current(skipped_item)

    pdf_sha: str | None = None
    if not options.force and has_current_extraction:
        pdf_sha = file_sha256(item.pdf_path)
        pdf_payload = provenance.get("pdf", {}) if provenance else {}
        if not isinstance(pdf_payload, dict):
            pdf_payload = {}
        if pdf_payload.get("sha256") == pdf_sha:
            page_count = cached_pages
            if page_count is None:
                page_count = provenance_cached_pages(
                    provenance,
                    pdf_sha=pdf_sha,
                    pdf_size=pdf_size,
                    pdf_mtime_ns=pdf_mtime_ns,
                )
            page_tier = classify_page_tier(page_count, options)
            skipped_item = dataclasses.replace(
                item,
                page_count=page_count,
                page_tier=page_tier,
                pdf_sha=pdf_sha,
                pdf_size=pdf_size,
                pdf_mtime_ns=pdf_mtime_ns,
            )
            return None, outcome_for_skipped_current(skipped_item)

    page_count = cached_pages
    if page_count is None:
        if pdf_sha is None:
            page_count = provenance_cached_pages(
                provenance,
                pdf_sha=None,
                pdf_size=pdf_size,
                pdf_mtime_ns=pdf_mtime_ns,
            )
        if page_count is None:
            page_count = pdf_page_count(item.pdf_path, timeout_seconds=options.pdfinfo_timeout_seconds)
    page_tier = classify_page_tier(page_count, options)
    return (
        dataclasses.replace(
            item,
            page_count=page_count,
            page_tier=page_tier,
            pdf_sha=pdf_sha,
            pdf_size=pdf_size,
            pdf_mtime_ns=pdf_mtime_ns,
        ),
        None,
    )


def increment_page_tier(summary: dict[str, int | float | str], page_tier: str) -> None:
    if page_tier == "unknown":
        summary["unknown_page_items"] = int(summary.get("unknown_page_items", 0)) + 1
    elif page_tier in {"article", "medium", "long", "huge"}:
        summary[f"{page_tier}_items"] = int(summary.get(f"{page_tier}_items", 0)) + 1
    else:
        summary["unknown_page_items"] = int(summary.get("unknown_page_items", 0)) + 1


def batched(items: list[FulltextWorkItem], batch_size: int) -> Iterable[tuple[int, list[FulltextWorkItem]]]:
    size = max(1, batch_size)
    for start in range(0, len(items), size):
        yield start // size + 1, items[start : start + size]


def process_item(
    item: FulltextWorkItem,
    *,
    options: FulltextSyncOptions,
    grobid_info: dict[str, str],
    parameters: list[tuple[str, str]],
    config_sha: str,
    timeout_read_seconds: float | None = None,
) -> FulltextOutcome:
    started = time.perf_counter()
    read_timeout = max(1.0, float(timeout_read_seconds or options.timeout_read_seconds))
    if options.dry_run:
        return FulltextOutcome(
            bib_file=str(item.bib_file),
            key=item.entry_key,
            status="planned",
            message="would extract full-text TEI",
            pdf_path=str(item.pdf_path),
            tei_path=str(item.tei_path),
            page_count=item.page_count,
            page_tier=item.page_tier,
        )

    stat = item.pdf_path.stat()
    pdf_sha = item.pdf_sha or file_sha256(item.pdf_path)
    pdf_size = item.pdf_size or stat.st_size
    pdf_mtime_ns = item.pdf_mtime_ns or stat.st_mtime_ns

    if not options.force and metadata_is_current(
        item.provenance_path,
        item.tei_path,
        pdf_sha=pdf_sha,
        grobid_info=grobid_info,
        config_sha=config_sha,
        parameters=parameters,
    ):
        return FulltextOutcome(
            bib_file=str(item.bib_file),
            key=item.entry_key,
            status="skipped_current",
            message="TEI already current for PDF hash and GROBID config",
            pdf_path=str(item.pdf_path),
            tei_path=str(item.tei_path),
            page_count=item.page_count,
            page_tier=item.page_tier,
        )

    url = urljoin(options.grobid_url.rstrip("/") + "/", DEFAULT_ENDPOINT.lstrip("/"))
    started_at = now_iso()
    try:
        response: requests.Response | None = None
        for attempt in range(1, options.grobid_max_attempts + 1):
            with item.pdf_path.open("rb") as handle:
                response = grobid_http_session().post(
                    url,
                    files={"input": (item.pdf_path.name, handle, "application/pdf", {"Expires": "0"})},
                    data=parameters,
                    timeout=(options.timeout_connect_seconds, read_timeout),
                )
            if response.status_code != 503 or attempt >= options.grobid_max_attempts:
                break
            sleep_seconds = options.grobid_busy_sleep_seconds * attempt
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        if response is None:
            raise RuntimeError("GROBID request did not produce a response")
        response.raise_for_status()
        tei = response.text
        features = tei_features(tei, bib_title=item.title, bib_author=item.author)
        tei_sha = text_sha256(tei)
        atomic_write_text(item.tei_path, tei if tei.endswith("\n") else tei + "\n")
        finished_at = now_iso()
        elapsed = time.perf_counter() - started
        provenance = {
            "schema_version": 1,
            "status": "ok",
            "entry": {
                "key": item.entry_key,
                "entry_type": item.entry_type,
                "bib_file": str(item.bib_file),
                "title": item.title,
                "author": item.author,
            },
            "paths": {
                "document_dir": str(item.document_dir),
                "pdf": str(item.pdf_path),
                "tei": str(item.tei_path),
            },
            "pdf": {
                "sha256": pdf_sha,
                "bytes": pdf_size,
                "mtime_ns": pdf_mtime_ns,
                "pages": item.page_count,
                "page_tier": item.page_tier,
            },
            "grobid": {
                **grobid_info,
                "base_url": options.grobid_url,
                "endpoint": DEFAULT_ENDPOINT,
                "parameters": parameters,
                "extraction_config_sha256": config_sha,
                "timeout_read_seconds": read_timeout,
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": round(elapsed, 3),
                "http_status": response.status_code,
                "attempts": attempt,
            },
            "tei": {
                "sha256": tei_sha,
                "bytes": len(tei.encode("utf-8")),
                **features,
            },
        }
        atomic_write_text(item.provenance_path, json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        return FulltextOutcome(
            bib_file=str(item.bib_file),
            key=item.entry_key,
            status="extracted",
            message="full-text TEI extracted",
            pdf_path=str(item.pdf_path),
            tei_path=str(item.tei_path),
            elapsed_seconds=round(elapsed, 3),
            tei_bytes=len(tei.encode("utf-8")),
            page_count=item.page_count,
            page_tier=item.page_tier,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        error_payload = {
            "schema_version": 1,
            "status": "error",
            "entry": {
                "key": item.entry_key,
                "entry_type": item.entry_type,
                "bib_file": str(item.bib_file),
                "title": item.title,
                "author": item.author,
            },
            "paths": {
                "document_dir": str(item.document_dir),
                "pdf": str(item.pdf_path),
                "tei": str(item.tei_path),
            },
            "pdf": {
                "sha256": pdf_sha,
                "bytes": pdf_size,
                "mtime_ns": pdf_mtime_ns,
                "pages": item.page_count,
                "page_tier": item.page_tier,
            },
            "grobid": {
                **grobid_info,
                "base_url": options.grobid_url,
                "endpoint": DEFAULT_ENDPOINT,
                "parameters": parameters,
                "extraction_config_sha256": config_sha,
                "timeout_read_seconds": read_timeout,
                "started_at": started_at,
                "finished_at": now_iso(),
                "elapsed_seconds": round(elapsed, 3),
                "attempts": locals().get("attempt", 0),
            },
            "error": str(exc),
        }
        if not options.dry_run:
            atomic_write_text(item.provenance_path, json.dumps(error_payload, indent=2, sort_keys=True) + "\n")
        return FulltextOutcome(
            bib_file=str(item.bib_file),
            key=item.entry_key,
            status="failed",
            message=str(exc),
            pdf_path=str(item.pdf_path),
            tei_path=str(item.tei_path),
            elapsed_seconds=round(elapsed, 3),
            page_count=item.page_count,
            page_tier=item.page_tier,
        )


def run_fulltext_sync(options: FulltextSyncOptions) -> FulltextSyncResult:
    options = dataclasses.replace(
        options,
        workers=max(0, int(options.workers)),
        medium_workers=max(0, int(options.medium_workers)),
        long_workers=max(0, int(options.long_workers)),
        huge_workers=max(0, int(options.huge_workers)),
        tei_coordinate_elements=tuple(str(v).strip() for v in options.tei_coordinate_elements if str(v).strip())
        or DEFAULT_TEI_COORDINATES,
        timeout_connect_seconds=max(1.0, float(options.timeout_connect_seconds)),
        timeout_read_seconds=max(1.0, float(options.timeout_read_seconds)),
        medium_timeout_read_seconds=max(1.0, float(options.medium_timeout_read_seconds)),
        long_timeout_read_seconds=max(1.0, float(options.long_timeout_read_seconds)),
        huge_timeout_read_seconds=max(1.0, float(options.huge_timeout_read_seconds)),
        dispatch_batch_size=max(1, int(options.dispatch_batch_size)),
        grobid_max_attempts=max(1, int(options.grobid_max_attempts)),
        grobid_busy_sleep_seconds=max(0.0, float(options.grobid_busy_sleep_seconds)),
    )
    tier_plan = effective_tier_plan(options)
    progress = ProgressLogger(options.progress_log, console_progress=options.console_progress)
    failures: list[FulltextOutcome] = []
    try:
        work, preflight, summary = scan_work(options)
        summary["cpu_threads"] = max(1, int(os.cpu_count() or 1))
        for tier in PAGE_TIER_ORDER:
            summary[f"{tier}_workers"] = tier_plan[tier].workers
            summary[f"{tier}_timeout_read_seconds"] = tier_plan[tier].timeout_read_seconds
        for outcome in preflight:
            progress.emit(dataclasses.asdict(outcome))

        parameters = grobid_parameters(options)
        config_sha = extraction_config_sha256(parameters)
        timeout = (max(1.0, options.timeout_connect_seconds), max(1.0, options.timeout_read_seconds))
        grobid_info = {"version": "unknown", "revision": "unknown"}
        if work and not options.dry_run:
            try:
                grobid_info = grobid_version(options.grobid_url, timeout)
            except Exception as exc:
                outcome = FulltextOutcome("*", "*", "failed", f"GROBID version check failed: {exc}")
                progress.emit(dataclasses.asdict(outcome))
                summary["failed"] = len(work)
                return FulltextSyncResult(summary=summary, failures=[outcome])

        counts: dict[str, int] = {}

        def record_outcome(outcome: FulltextOutcome) -> None:
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
            if outcome.status == "failed":
                failures.append(outcome)
            progress.emit(dataclasses.asdict(outcome))

        batch_size = max(1, int(options.dispatch_batch_size))
        for batch_index, batch in batched(work, batch_size):
            progress.emit(
                {
                    "status": "batch_start",
                    "bib_file": "*",
                    "key": "*",
                    "message": f"preparing batch {batch_index}: {len(batch)} item(s)",
                }
            )
            buckets: dict[str, list[FulltextWorkItem]] = {tier: [] for tier in PAGE_TIER_ORDER}
            for item in batch:
                prepared, outcome = prepare_item(
                    item,
                    options=options,
                    grobid_info=grobid_info,
                    config_sha=config_sha,
                    parameters=parameters,
                )
                if outcome is not None:
                    increment_page_tier(summary, outcome.page_tier)
                    record_outcome(outcome)
                    continue
                if prepared is None:
                    continue
                increment_page_tier(summary, prepared.page_tier)
                buckets.setdefault(prepared.page_tier, []).append(prepared)

            for tier in PAGE_TIER_ORDER:
                bucket = buckets.get(tier, [])
                if not bucket:
                    continue
                plan = tier_plan[tier]
                progress.emit(
                    {
                        "status": "tier_start",
                        "bib_file": "*",
                        "key": "*",
                        "page_tier": tier,
                        "message": (
                            f"batch {batch_index} {tier}: {len(bucket)} item(s), "
                            f"workers={plan.workers}, timeout_read={plan.timeout_read_seconds:g}s"
                        ),
                    }
                )

                if options.dry_run or len(bucket) <= 1:
                    for item in bucket:
                        outcome = process_item(
                            item,
                            options=options,
                            grobid_info=grobid_info,
                            parameters=parameters,
                            config_sha=config_sha,
                            timeout_read_seconds=plan.timeout_read_seconds,
                        )
                        record_outcome(outcome)
                    continue

                with concurrent.futures.ThreadPoolExecutor(max_workers=plan.workers) as executor:
                    futures = [
                        executor.submit(
                            process_item,
                            item,
                            options=options,
                            grobid_info=grobid_info,
                            parameters=parameters,
                            config_sha=config_sha,
                            timeout_read_seconds=plan.timeout_read_seconds,
                        )
                        for item in bucket
                    ]
                    for future in concurrent.futures.as_completed(futures):
                        record_outcome(future.result())

        for key, value in sorted(counts.items()):
            summary[key] = value
        summary["failed"] = counts.get("failed", 0)
        summary["grobid_version"] = grobid_info.get("version", "unknown")
        summary["grobid_revision"] = grobid_info.get("revision", "unknown")
        return FulltextSyncResult(summary=summary, failures=failures)
    finally:
        progress.close()
