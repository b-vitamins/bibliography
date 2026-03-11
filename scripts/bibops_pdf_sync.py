#!/usr/bin/env python3
"""PDF synchronization engine used by bibops `pdf-sync`."""

from __future__ import annotations

import dataclasses
import datetime as dt
import glob
import hashlib
import json
import os
import random
import re
import signal
import shutil
import sys
import tempfile
import threading
import time
import tomllib
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

import bibtexparser
import requests
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_DIR = Path("/home/b/documents")
CHECKPOINT_VERSION = 1
FAILED_ENTRY_CLASSIFIER_VERSION = "2"
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
SEMANTIC_SCHOLAR_PAPER_API = "https://api.semanticscholar.org/graph/v1/paper"
_TRANSIENT_FAILURE_MARKERS = (
    "http 408",
    "http 425",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "timed out",
    "timeout",
    "temporar",
    "connection",
    "chunkedencodingerror",
    "contentdecodingerror",
    "name or service not known",
    "temporary failure in name resolution",
    "connection reset",
    "connection aborted",
    "broken pipe",
    "ssl",
)

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

DEFAULT_HOST_MIN_INTERVAL_BY_HOST: dict[str, float] = {
    "openreview.net": 1.0,
    "api.openreview.net": 1.0,
    "arxiv.org": 2.0,
    "export.arxiv.org": 5.0,
    "proceedings.mlr.press": 1.0,
    "proceedings.neurips.cc": 1.4,
    "papers.nips.cc": 1.5,
    "dl.acm.org": 2.0,
    "aclanthology.org": 1.2,
    "ieeexplore.ieee.org": 2.0,
    "link.springer.com": 2.0,
}


@dataclasses.dataclass
class PdfSyncOptions:
    targets: list[str]
    base_dir: Path = DEFAULT_BASE_DIR
    download: bool = True
    fix_existing: bool = True
    dry_run: bool = False
    verify_existing: bool = True
    smart_url_derivation: bool = True
    max_entries: int = 0
    max_attempts: int = 6
    timeout_connect_seconds: float = 10.0
    timeout_read_seconds: float = 90.0
    max_attempt_wall_seconds: float = 240.0
    max_pdf_size_mb: int = 300
    min_pdf_size_bytes: int = 1024
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 180.0
    backoff_jitter_seconds: float = 0.4
    host_default_min_interval_seconds: float = 0.8
    host_min_interval_seconds_by_host: dict[str, float] = dataclasses.field(default_factory=dict)
    checkpoint_path: Path | None = Path("ops/pdf-sync-checkpoint.json")
    resume: bool = True
    retry_failures: bool = False
    progress_log: Path | None = None
    console_progress: bool = False
    checkpoint_flush_seconds: float = 20.0
    max_consecutive_failures: int = 50
    user_agent: str = "bibops-pdf-sync/1.0"
    policy_path: Path | None = None


@dataclasses.dataclass
class EntryOutcome:
    bib_file: str
    key: str
    status: str
    message: str
    url: str | None = None
    target_path: str | None = None
    attempts: int = 0
    bytes_written: int = 0


@dataclasses.dataclass
class PdfSyncResult:
    summary: dict[str, int | str]
    failures: list[EntryOutcome]


@dataclasses.dataclass
class DownloadAttemptResult:
    ok: bool
    message: str
    final_url: str = ""
    status_code: int | None = None
    attempts: int = 0
    bytes_written: int = 0


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_bib(path: Path):
    data = path.read_text(encoding="utf-8")
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    try:
        return bibtexparser.loads(data, parser=parser)
    except Exception:
        parser_fallback = BibTexParser(common_strings=True)
        parser_fallback.ignore_nonstandard_types = False
        return bibtexparser.loads(data, parser=parser_fallback)


def write_bib(path: Path, bib_db: Any) -> None:
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None  # type: ignore[assignment]
    writer.align_values = False
    path.write_text(writer.write(bib_db), encoding="utf-8")


def parse_file_field(field_value: str | None) -> tuple[str | None, str | None]:
    if not field_value:
        return None, None

    raw = field_value.strip()
    if not raw:
        return None, None

    segments = [s.strip() for s in raw.split(";") if s.strip()]
    for seg in segments:
        m = re.match(r"^:(.+):([A-Za-z0-9_+\-]+)$", seg)
        if m:
            return m.group(1).strip(), m.group(2).strip().lower()

        m = re.match(r"^(.+):([A-Za-z0-9_+\-]+)$", seg)
        if m:
            maybe_path = m.group(1).strip()
            maybe_type = m.group(2).strip().lower()
            if "/" in maybe_path or maybe_path.lower().endswith(".pdf"):
                return maybe_path, maybe_type

        if seg.lower().endswith(".pdf") or "/" in seg:
            return seg, "pdf"

    return None, None


def format_file_field(path: Path, file_type: str = "pdf") -> str:
    return f":{path}:{file_type}"


def normalize_host(host: str) -> str:
    return host.strip().lower().lstrip(".")


def host_of(url: str) -> str:
    parsed = urlparse(url)
    return normalize_host(parsed.netloc)


def normalize_url(url: str, fallback_base_url: str | None = None) -> str:
    u = (url or "").strip().strip("{}")
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("//"):
        return f"https:{u}"
    if u.startswith("/") and fallback_base_url:
        base = urlparse(fallback_base_url)
        if base.scheme and base.netloc:
            return f"{base.scheme}://{base.netloc}{u}"
    return ""


def normalize_doi(doi_raw: str) -> str:
    raw = (doi_raw or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            lowered = raw.lower()
            break
    return raw.strip().strip("/")


def doi_from_url(url: str) -> str:
    normalized = normalize_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    host = normalize_host(parsed.netloc)
    if host not in {"doi.org", "dx.doi.org"}:
        return ""
    return normalize_doi(parsed.path.lstrip("/"))


def entry_doi(entry: dict[str, Any]) -> str:
    direct = normalize_doi(str(entry.get("doi", "")).strip())
    if direct:
        return direct
    for field in ("pdf", "url"):
        doi = doi_from_url(str(entry.get(field, "")).strip())
        if doi:
            return doi
    return ""


def maybe_set_pdf_field(entry: dict[str, Any], url: str, *, dry_run: bool) -> bool:
    normalized = normalize_url(url, fallback_base_url=str(entry.get("url", "")).strip())
    if not normalized or not looks_like_pdf_url(normalized):
        return False

    current_pdf = normalize_url(str(entry.get("pdf", "")).strip(), fallback_base_url=str(entry.get("url", "")).strip())
    if current_pdf and canonicalize_url(current_pdf) == canonicalize_url(normalized):
        return False

    if dry_run:
        return True
    entry["pdf"] = normalized
    return True


def semantic_scholar_open_access_pdf_url(
    session: requests.Session,
    doi: str,
    *,
    timeout_connect: float,
    timeout_read: float,
    user_agent: str,
) -> str:
    token = normalize_doi(doi)
    if not token:
        return ""

    # Semantic Scholar expects DOI path segment with slash separators preserved.
    endpoint = f"{SEMANTIC_SCHOLAR_PAPER_API}/DOI:{quote(token, safe='/')}"
    params = {"fields": "openAccessPdf,url,isOpenAccess,title"}
    headers = {"User-Agent": user_agent}
    try:
        response = session.get(
            endpoint,
            params=params,
            timeout=(timeout_connect, timeout_read),
            allow_redirects=True,
            headers=headers,
        )
    except Exception:
        return ""
    if response.status_code != 200:
        return ""
    try:
        payload = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    open_access = payload.get("openAccessPdf")
    if not isinstance(open_access, dict):
        return ""
    candidate = normalize_url(str(open_access.get("url", "")).strip())
    if not candidate:
        return ""
    return candidate


def parse_retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)

    try:
        when = parsedate_to_datetime(raw)
    except Exception:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    delta = (when.astimezone(dt.timezone.utc) - dt.datetime.now(dt.timezone.utc)).total_seconds()
    return max(0.0, delta)


def compute_entry_fingerprint(entry: dict[str, Any]) -> str:
    fields = [
        str(entry.get("ID", "")).strip(),
        str(entry.get("pdf", "")).strip(),
        str(entry.get("url", "")).strip(),
        str(entry.get("arxiv", "")).strip(),
        str(entry.get("title", "")).strip(),
    ]
    joined = "\u241f".join(fields)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def verify_pdf(path: Path, min_size_bytes: int = 1024) -> tuple[bool, str]:
    try:
        with path.open("rb") as handle:
            header = handle.read(5)
            if header != b"%PDF-":
                return False, "missing PDF header"

            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size < min_size_bytes:
                return False, f"file too small ({size} bytes)"

            tail_size = min(4096, size)
            handle.seek(-tail_size, os.SEEK_END)
            tail = handle.read(tail_size)
            if b"%%EOF" not in tail:
                return False, "missing EOF marker"
    except Exception as exc:
        return False, f"verification error: {exc}"

    return True, "ok"


def default_host_intervals() -> dict[str, float]:
    return dict(DEFAULT_HOST_MIN_INTERVAL_BY_HOST)


def parse_host_interval_overrides(raw_values: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for raw in raw_values:
        chunk = raw.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"invalid --host-interval value `{chunk}` (expected host=seconds)")
        host_part, seconds_part = chunk.split("=", 1)
        host = normalize_host(host_part)
        if not host:
            raise ValueError(f"invalid host in --host-interval `{chunk}`")
        try:
            seconds = float(seconds_part)
        except ValueError as exc:
            raise ValueError(f"invalid seconds in --host-interval `{chunk}`") from exc
        if seconds < 0:
            raise ValueError(f"seconds must be >= 0 in --host-interval `{chunk}`")
        out[host] = seconds
    return out


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    canonical = f"{scheme}://{netloc}{path}"
    if query:
        canonical = f"{canonical}?{query}"
    return canonical


def looks_like_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    if path.endswith(".pdf"):
        return True
    if "/pdf/" in path or path.endswith("/pdf"):
        return True
    if "format=pdf" in query or "download=pdf" in query:
        return True
    if "pdf=" in query:
        return True
    return False


def build_candidate_urls(entry: dict[str, Any], smart: bool) -> list[str]:
    pdf_url = str(entry.get("pdf", "")).strip()
    url_field = str(entry.get("url", "")).strip()
    arxiv_field = str(entry.get("arxiv", "")).strip()
    doi_field = entry_doi(entry)

    strong_candidates: list[str] = []
    fallback_candidates: list[str] = []
    seen: set[str] = set()

    def add(url: str, strong: bool) -> None:
        normalized = normalize_url(url, fallback_base_url=url_field)
        if not normalized:
            return
        key = canonicalize_url(normalized)
        if key in seen:
            return
        seen.add(key)
        if strong:
            strong_candidates.append(normalized)
        else:
            fallback_candidates.append(normalized)

    if pdf_url:
        add(pdf_url, strong=True)
    if doi_field:
        add(f"https://doi.org/{doi_field}", strong=False)

    if smart:
        for raw in (pdf_url, url_field, arxiv_field, f"https://doi.org/{doi_field}" if doi_field else ""):
            for derived in derive_urls(raw, context_url=url_field):
                add(derived, strong=True)

    for raw in (url_field, arxiv_field, f"https://doi.org/{doi_field}" if doi_field else ""):
        normalized = normalize_url(raw, fallback_base_url=url_field)
        if not normalized:
            continue
        add(normalized, strong=looks_like_pdf_url(normalized))

    if strong_candidates:
        return strong_candidates
    if smart:
        return fallback_candidates

    return []


def derive_urls(raw: str, context_url: str = "") -> list[str]:
    url = normalize_url(raw, fallback_base_url=context_url)
    if not url:
        return []

    out: list[str] = []
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or ""
    query = parsed.query

    if host.endswith("openreview.net"):
        query_id = parse_qs(query).get("id", [""])[0].strip()
        if query_id:
            out.append(f"https://openreview.net/pdf?id={query_id}")
        if path.startswith("/forum") and query_id:
            out.append(f"https://openreview.net/pdf?id={query_id}")
        if path.startswith("/pdf/"):
            out.append(url)

    if host.endswith("arxiv.org"):
        if path.startswith("/abs/"):
            ident = path[len("/abs/") :].strip("/")
            if ident:
                out.append(f"https://arxiv.org/pdf/{ident}.pdf")
        if path.startswith("/pdf/") and not path.endswith(".pdf"):
            out.append(f"{url}.pdf")

    if host.endswith("proceedings.mlr.press") and path.endswith(".html"):
        out.append(url[:-5] + ".pdf")

    if host.endswith("nips.cc") or host.endswith("neurips.cc"):
        if "-Abstract" in path and path.endswith(".html"):
            out.append(url.replace("-Abstract", "-Paper").replace(".html", ".pdf"))
        elif path.endswith(".html"):
            out.append(url[:-5] + ".pdf")

    if host.endswith("aclanthology.org"):
        ident = path.strip("/")
        if ident and not ident.endswith(".pdf"):
            out.append(f"https://aclanthology.org/{ident}.pdf")

    if host == "dl.acm.org" and path.startswith("/doi/") and not path.startswith("/doi/pdf/"):
        doi_suffix = path[len("/doi/") :].strip("/")
        if doi_suffix:
            out.append(f"https://dl.acm.org/doi/pdf/{doi_suffix}")

    if host in {"doi.org", "dx.doi.org"}:
        doi_suffix = normalize_doi(path.lstrip("/"))
        if doi_suffix:
            lowered = doi_suffix.lower()
            if lowered.startswith("10.1145/"):
                out.append(f"https://dl.acm.org/doi/pdf/{doi_suffix}")
            arxiv_match = re.match(r"10\.48550/arxiv\.(.+)$", lowered)
            if arxiv_match:
                arxiv_id = arxiv_match.group(1)
                out.append(f"https://arxiv.org/pdf/{arxiv_id}.pdf")
            pii_match = re.match(r"10\.1016/(b[0-9x\-.]+)$", lowered)
            if pii_match:
                pii = pii_match.group(1).replace("-", "").replace(".", "").upper()
                if pii:
                    out.append(
                        f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?isDTMRedir=true&download=true"
                    )

    return out


def expand_targets(targets: list[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    unresolved: list[str] = []
    for target in targets:
        matches = glob.glob(target, recursive=True)
        if not matches:
            p = Path(target)
            if p.exists():
                matches = [target]

        if not matches:
            unresolved.append(target)
            continue

        for item in matches:
            path = Path(item)
            if path.is_file() and path.suffix.lower() == ".bib":
                paths.append(path)

    deduped = sorted({p.resolve() for p in paths})
    return deduped, unresolved


def get_target_path(entry: dict[str, Any], base_dir: Path) -> Path:
    entry_type = str(entry.get("ENTRYTYPE", "misc")).strip().lower() or "misc"
    subdir = TYPE_TO_DIR.get(entry_type, "misc")
    key = str(entry.get("ID", "unknown")).strip() or "unknown"
    target_dir = base_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{key}.pdf"


class HostCadenceController:
    def __init__(self, default_interval: float, per_host: dict[str, float], jitter_seconds: float):
        self.default_interval = max(0.0, default_interval)
        self.per_host = {normalize_host(k): max(0.0, v) for k, v in per_host.items()}
        self.jitter_seconds = max(0.0, jitter_seconds)
        self.next_allowed_at: dict[str, float] = {}

    def wait(self, host: str) -> float:
        h = normalize_host(host)
        now = time.monotonic()
        next_allowed = self.next_allowed_at.get(h, 0.0)
        delay = max(0.0, next_allowed - now)
        if delay > 0:
            time.sleep(delay)
        return delay

    def mark_request(self, host: str) -> None:
        h = normalize_host(host)
        interval = self.per_host.get(h, self.default_interval)
        jitter = random.uniform(0.0, self.jitter_seconds) if self.jitter_seconds > 0 else 0.0
        self.next_allowed_at[h] = time.monotonic() + interval + jitter

    def penalize(self, host: str, seconds: float) -> None:
        if seconds <= 0:
            return
        h = normalize_host(host)
        penalty_until = time.monotonic() + seconds
        self.next_allowed_at[h] = max(self.next_allowed_at.get(h, 0.0), penalty_until)


class CheckpointStore:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {
            "version": CHECKPOINT_VERSION,
            "updated_at": now_iso(),
            "entries": {},
        }
        self._dirty = False

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(loaded, dict):
            return
        entries = loaded.get("entries")
        if not isinstance(entries, dict):
            return
        self.data = {
            "version": int(loaded.get("version", CHECKPOINT_VERSION)),
            "updated_at": str(loaded.get("updated_at", now_iso())),
            "entries": entries,
        }

    def get(self, entry_id: str) -> dict[str, Any] | None:
        raw = self.data.get("entries", {})
        if not isinstance(raw, dict):
            return None
        item = raw.get(entry_id)
        if isinstance(item, dict):
            return item
        return None

    def should_skip(self, entry_id: str, fingerprint: str, retry_failures: bool) -> bool:
        item = self.get(entry_id)
        if not item:
            return False
        if str(item.get("fingerprint", "")) != fingerprint:
            return False

        status = str(item.get("status", "")).strip()
        if status in {"downloaded", "already_present", "linked_existing"}:
            target_path = str(item.get("target_path", "")).strip()
            if target_path and Path(target_path).exists():
                return True
            return False
        if status in {"no_source"}:
            return True
        if status == "failed":
            if not retry_failures:
                return True
            classifier_version = str(item.get("failed_entry_classifier_version", "")).strip()
            message = str(item.get("message", "")).strip()
            # Legacy checkpoint entries (before classifier versioning) should still
            # be skipped when the recorded failure is clearly permanent.
            if classifier_version != FAILED_ENTRY_CLASSIFIER_VERSION:
                if message and not failure_message_looks_transient(message):
                    return True
                return False
            # With retry enabled, only retry transient operational failures.
            if not failure_message_looks_transient(message):
                return True
        return False

    def record(self, entry_id: str, fingerprint: str, outcome: EntryOutcome) -> None:
        entries = self.data.setdefault("entries", {})
        if not isinstance(entries, dict):
            self.data["entries"] = {}
            entries = self.data["entries"]
        entries[entry_id] = {
            "fingerprint": fingerprint,
            "status": outcome.status,
            "message": outcome.message,
            "url": outcome.url or "",
            "target_path": outcome.target_path or "",
            "attempts": outcome.attempts,
            "bytes_written": outcome.bytes_written,
            "failed_entry_classifier_version": FAILED_ENTRY_CLASSIFIER_VERSION,
            "updated_at": now_iso(),
        }
        self.data["updated_at"] = now_iso()
        self._dirty = True

    def save(self, force: bool = False) -> None:
        if not self._dirty and not force:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)
        self._dirty = False


class ProgressLogger:
    def __init__(self, path: Path | None, *, console_progress: bool = False):
        self.path = path
        self.console_progress = console_progress
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, payload: dict[str, Any]) -> None:
        event = dict(payload)
        event["timestamp"] = now_iso()

        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True))
                handle.write("\n")

        if self.console_progress:
            ts = str(event.get("timestamp", ""))
            status = str(event.get("status", "")).strip() or "event"
            bib = str(event.get("bib_file", "")).strip()
            key = str(event.get("key", "")).strip()
            msg = str(event.get("message", "")).strip()
            if bib:
                bib = Path(bib).name
            parts = [f"[{ts}]", status]
            if bib:
                parts.append(bib)
            if key:
                parts.append(key)
            if msg:
                parts.append(msg)
            print(" | ".join(parts), file=sys.stderr, flush=True)


def build_http_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    retry = Retry(total=0, connect=0, read=0, status=0, redirect=3)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=32)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
    )
    return session


def should_retry_error(exc: BaseException) -> bool:
    transient_types = (
        TimeoutError,
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
        requests.exceptions.ContentDecodingError,
    )
    return isinstance(exc, transient_types)


@contextmanager
def attempt_deadline(seconds: float):
    """Best-effort wall-clock cap for a single HTTP attempt."""
    if seconds <= 0:
        yield
        return

    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        yield
        return

    if threading.current_thread() is not threading.main_thread():
        yield
        return

    seconds = max(0.1, float(seconds))
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(signum, frame):  # type: ignore[unused-argument]
        raise TimeoutError(f"attempt exceeded wall timeout ({seconds:.1f}s)")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def failure_message_looks_transient(message: str) -> bool:
    msg = (message or "").lower()
    if not msg:
        return True
    if re.search(r"\bhttp(?:\s+status)?\s+(408|425|429|500|502|503|504)\b", msg):
        return True
    for marker in _TRANSIENT_FAILURE_MARKERS:
        if marker in msg:
            return True
    return False


def counts_toward_abort_budget(outcome: EntryOutcome) -> bool:
    """Return True when this failure likely indicates an operational outage."""
    if outcome.status != "failed":
        return False

    message = (outcome.message or "").lower()
    if not message:
        return True

    if failure_message_looks_transient(message):
        return True

    # Permanent source-level failures should not trip global outage aborts.
    if "http 4" in message:
        return False
    if "unexpected content-type" in message:
        return False
    if "invalid pdf" in message:
        return False
    if "no candidate url" in message or "no candidate urls" in message:
        return False

    # Conservative default for unknown failure text.
    return True


def supplemental_open_access_candidates(
    entry: dict[str, Any],
    session: requests.Session,
    options: PdfSyncOptions,
    cache: dict[str, list[str]],
) -> list[str]:
    doi = entry_doi(entry)
    if not doi:
        return []
    cached = cache.get(doi)
    if cached is not None:
        return list(cached)

    discovered: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        normalized = normalize_url(url, fallback_base_url=str(entry.get("url", "")).strip())
        if not normalized:
            return
        key = canonicalize_url(normalized)
        if key in seen:
            return
        seen.add(key)
        discovered.append(normalized)

    # Semantic Scholar open-access pointer is a good low-cost fallback for DOI-based records.
    s2_url = semantic_scholar_open_access_pdf_url(
        session=session,
        doi=doi,
        timeout_connect=options.timeout_connect_seconds,
        timeout_read=min(options.timeout_read_seconds, 30.0),
        user_agent=options.user_agent,
    )
    if s2_url:
        add(s2_url)

    cache[doi] = list(discovered)
    return list(discovered)


def backoff_delay_seconds(options: PdfSyncOptions, attempt: int, retry_after: float | None) -> float:
    exp_delay = options.backoff_base_seconds * (2 ** max(0, attempt - 1))
    jitter = random.uniform(0.0, options.backoff_jitter_seconds) if options.backoff_jitter_seconds > 0 else 0.0
    planned = min(options.backoff_max_seconds, exp_delay + jitter)
    if retry_after is not None:
        planned = max(planned, min(options.backoff_max_seconds, retry_after))
    return max(0.0, planned)


def download_pdf(
    session: requests.Session,
    cadence: HostCadenceController,
    url: str,
    target_path: Path,
    options: PdfSyncOptions,
    attempt_logger: Callable[[dict[str, Any]], None] | None = None,
) -> DownloadAttemptResult:
    max_bytes = int(options.max_pdf_size_mb * 1024 * 1024)
    host = host_of(url)

    for attempt in range(1, options.max_attempts + 1):
        temp_path: Path | None = None
        try:
            if attempt_logger:
                attempt_logger(
                    {
                        "status": "download_attempt",
                        "message": f"attempt {attempt}/{options.max_attempts}",
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": options.max_attempts,
                    }
                )
            cadence.wait(host)
            cadence.mark_request(host)

            with attempt_deadline(options.max_attempt_wall_seconds):
                with session.get(
                    url,
                    timeout=(options.timeout_connect_seconds, options.timeout_read_seconds),
                    stream=True,
                    allow_redirects=True,
                ) as response:
                    status = response.status_code
                    if status in RETRYABLE_STATUS_CODES:
                        retry_after = parse_retry_after_seconds(response.headers.get("Retry-After"))
                        delay = backoff_delay_seconds(options, attempt, retry_after)
                        cadence.penalize(host, delay)
                        if attempt < options.max_attempts:
                            if attempt_logger:
                                attempt_logger(
                                    {
                                        "status": "download_retry",
                                        "message": f"retryable HTTP {status}; sleeping {delay:.1f}s",
                                        "url": str(response.url or url),
                                        "attempt": attempt,
                                        "max_attempts": options.max_attempts,
                                        "delay_seconds": round(delay, 3),
                                    }
                                )
                            time.sleep(delay)
                            continue
                        return DownloadAttemptResult(
                            ok=False,
                            message=f"retryable HTTP status {status} after {attempt} attempts",
                            status_code=status,
                            attempts=attempt,
                        )

                    if status >= 400:
                        return DownloadAttemptResult(
                            ok=False,
                            message=f"HTTP {status}",
                            status_code=status,
                            attempts=attempt,
                        )

                    content_length = response.headers.get("Content-Length")
                    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                        return DownloadAttemptResult(
                            ok=False,
                            message=f"content-length exceeds max size ({content_length} bytes)",
                            status_code=status,
                            attempts=attempt,
                        )

                    content_type = response.headers.get("Content-Type", "").lower()
                    if "html" in content_type and not (
                        url.lower().endswith(".pdf") or str(response.url).lower().endswith(".pdf")
                    ):
                        return DownloadAttemptResult(
                            ok=False,
                            message=f"unexpected content-type `{content_type}`",
                            status_code=status,
                            attempts=attempt,
                        )

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    fd, raw_temp = tempfile.mkstemp(
                        prefix="pdf-sync-",
                        suffix=".part",
                        dir=str(target_path.parent),
                    )
                    os.close(fd)
                    temp_path = Path(raw_temp)

                    total = 0
                    with temp_path.open("wb") as out_handle:
                        for chunk in response.iter_content(chunk_size=16 * 1024):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_bytes:
                                raise RuntimeError("download exceeded max configured size")
                            out_handle.write(chunk)

            is_valid, reason = verify_pdf(temp_path, min_size_bytes=options.min_pdf_size_bytes)
            if not is_valid:
                return DownloadAttemptResult(
                    ok=False,
                    message=f"invalid pdf: {reason}",
                    status_code=status,
                    attempts=attempt,
                )

            os.replace(temp_path, target_path)
            return DownloadAttemptResult(
                ok=True,
                message="downloaded",
                final_url=response.url,
                status_code=status,
                attempts=attempt,
                bytes_written=total,
            )

        except Exception as exc:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

            retryable = should_retry_error(exc) or "max configured size" in str(exc)
            if retryable and attempt < options.max_attempts:
                delay = backoff_delay_seconds(options, attempt, retry_after=None)
                cadence.penalize(host, delay)
                if attempt_logger:
                    attempt_logger(
                        {
                            "status": "download_retry",
                            "message": f"{exc}; sleeping {delay:.1f}s",
                            "url": url,
                            "attempt": attempt,
                            "max_attempts": options.max_attempts,
                            "delay_seconds": round(delay, 3),
                        }
                    )
                time.sleep(delay)
                continue

            return DownloadAttemptResult(
                ok=False,
                message=str(exc),
                attempts=attempt,
            )

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    return DownloadAttemptResult(ok=False, message="exhausted attempts", attempts=options.max_attempts)


def apply_policy_overrides(options: PdfSyncOptions) -> PdfSyncOptions:
    if options.policy_path is None:
        return options
    policy_path = options.policy_path
    if not policy_path.exists():
        raise FileNotFoundError(f"PDF sync policy file not found: {policy_path}")

    data = tomllib.loads(policy_path.read_text(encoding="utf-8"))

    if isinstance(data.get("max_attempts"), int):
        options.max_attempts = max(1, int(data["max_attempts"]))
    if isinstance(data.get("timeout_connect_seconds"), (int, float)):
        options.timeout_connect_seconds = max(1.0, float(data["timeout_connect_seconds"]))
    if isinstance(data.get("timeout_read_seconds"), (int, float)):
        options.timeout_read_seconds = max(1.0, float(data["timeout_read_seconds"]))
    if isinstance(data.get("max_attempt_wall_seconds"), (int, float)):
        options.max_attempt_wall_seconds = max(0.0, float(data["max_attempt_wall_seconds"]))
    if isinstance(data.get("max_pdf_size_mb"), int):
        options.max_pdf_size_mb = max(1, int(data["max_pdf_size_mb"]))
    if isinstance(data.get("backoff_base_seconds"), (int, float)):
        options.backoff_base_seconds = max(0.0, float(data["backoff_base_seconds"]))
    if isinstance(data.get("backoff_max_seconds"), (int, float)):
        options.backoff_max_seconds = max(0.0, float(data["backoff_max_seconds"]))
    if isinstance(data.get("backoff_jitter_seconds"), (int, float)):
        options.backoff_jitter_seconds = max(0.0, float(data["backoff_jitter_seconds"]))
    if isinstance(data.get("host_default_min_interval_seconds"), (int, float)):
        options.host_default_min_interval_seconds = max(0.0, float(data["host_default_min_interval_seconds"]))
    if isinstance(data.get("max_consecutive_failures"), int):
        options.max_consecutive_failures = max(1, int(data["max_consecutive_failures"]))
    if isinstance(data.get("checkpoint_flush_seconds"), (int, float)):
        options.checkpoint_flush_seconds = max(0.0, float(data["checkpoint_flush_seconds"]))
    if isinstance(data.get("user_agent"), str) and data["user_agent"].strip():
        options.user_agent = data["user_agent"].strip()
    raw_host = data.get("host_min_interval_by_host")
    if isinstance(raw_host, dict):
        for host, interval in raw_host.items():
            if isinstance(host, str) and isinstance(interval, (int, float)):
                options.host_min_interval_seconds_by_host[normalize_host(host)] = max(0.0, float(interval))

    return options


def maybe_relink_or_fix_existing(
    entry: dict[str, Any],
    target_path: Path,
    options: PdfSyncOptions,
) -> tuple[bool, str]:
    file_value = str(entry.get("file", "")).strip()
    if not file_value:
        return False, ""

    parsed_path, parsed_type = parse_file_field(file_value)
    if not parsed_path:
        return False, ""

    existing_path = Path(parsed_path)
    if not existing_path.exists():
        if options.fix_existing:
            if options.dry_run:
                return True, "would_remove_dead_file_field"
            entry.pop("file", None)
            return True, "removed_dead_file_field"
        return False, ""

    if options.verify_existing:
        valid, reason = verify_pdf(existing_path, min_size_bytes=options.min_pdf_size_bytes)
        if not valid:
            if options.fix_existing:
                if options.dry_run:
                    return True, f"would_remove_invalid_file_field:{reason}"
                entry.pop("file", None)
                return True, f"removed_invalid_file_field:{reason}"
            return False, ""

    if not options.fix_existing:
        normalized = format_file_field(existing_path.resolve(), parsed_type or "pdf")
        if entry.get("file") != normalized:
            if options.dry_run:
                return True, "would_normalize_file_field"
            entry["file"] = normalized
            return True, "normalized_file_field"
        return False, ""

    if existing_path.resolve() == target_path.resolve():
        normalized = format_file_field(target_path.resolve(), parsed_type or "pdf")
        if entry.get("file") != normalized:
            if options.dry_run:
                return True, "would_normalize_file_field"
            entry["file"] = normalized
            return True, "normalized_file_field"
        return False, ""

    if options.dry_run:
        return True, "would_move_existing_file"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(existing_path), str(target_path))
    entry["file"] = format_file_field(target_path.resolve(), parsed_type or "pdf")
    return True, "moved_existing_file"


def process_entry(
    entry: dict[str, Any],
    bib_file: Path,
    options: PdfSyncOptions,
    session: requests.Session,
    cadence: HostCadenceController,
    checkpoint: CheckpointStore | None,
    progress: ProgressLogger,
    oa_lookup_cache: dict[str, list[str]],
) -> EntryOutcome:
    key = str(entry.get("ID", "")).strip() or "unknown"
    fingerprint = compute_entry_fingerprint(entry)
    checkpoint_key = f"{bib_file}:{key}"

    def record_checkpoint(outcome: EntryOutcome) -> None:
        if checkpoint and not options.dry_run:
            checkpoint.record(checkpoint_key, fingerprint, outcome)

    def emit_download_event(payload: dict[str, Any]) -> None:
        event = {
            "bib_file": str(bib_file),
            "key": key,
            **payload,
        }
        progress.emit(event)

    if checkpoint and options.resume and checkpoint.should_skip(checkpoint_key, fingerprint, options.retry_failures):
        repaired_from_checkpoint = False
        if checkpoint and options.fix_existing:
            existing = checkpoint.get(checkpoint_key)
            if existing:
                repaired_from_checkpoint = maybe_set_pdf_field(
                    entry,
                    str(existing.get("url", "")).strip(),
                    dry_run=options.dry_run,
                )
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="resumed_skip_repaired" if repaired_from_checkpoint else "resumed_skip",
            message="checkpoint skip (repaired pdf field)" if repaired_from_checkpoint else "checkpoint skip",
        )
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    target_path = get_target_path(entry, options.base_dir)

    changed, change_message = maybe_relink_or_fix_existing(entry, target_path, options)
    if changed and ("moved_existing_file" in change_message or "would_move_existing_file" in change_message):
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="linked_existing",
            message=change_message,
            target_path=str(target_path),
        )
        record_checkpoint(outcome)
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    if "file" in entry and not (
        change_message.startswith("removed_")
        or change_message.startswith("would_remove_")
    ):
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="linked_existing",
            message=change_message or "file field already present",
            target_path=str(target_path),
        )
        record_checkpoint(outcome)
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    if target_path.exists():
        if not options.verify_existing:
            if not options.dry_run:
                entry["file"] = format_file_field(target_path.resolve(), "pdf")
            outcome = EntryOutcome(
                bib_file=str(bib_file),
                key=key,
                status="already_present",
                message="linked existing target file",
                target_path=str(target_path),
            )
            record_checkpoint(outcome)
            progress.emit(dataclasses.asdict(outcome))
            return outcome

        valid, reason = verify_pdf(target_path, min_size_bytes=options.min_pdf_size_bytes)
        if valid:
            if not options.dry_run:
                entry["file"] = format_file_field(target_path.resolve(), "pdf")
            outcome = EntryOutcome(
                bib_file=str(bib_file),
                key=key,
                status="already_present",
                message="target file already valid",
                target_path=str(target_path),
            )
            record_checkpoint(outcome)
            progress.emit(dataclasses.asdict(outcome))
            return outcome

        if not options.dry_run:
            target_path.unlink(missing_ok=True)

    if not options.download:
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="no_download",
            message="download disabled by option",
            target_path=str(target_path),
        )
        record_checkpoint(outcome)
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    candidates = build_candidate_urls(entry, smart=options.smart_url_derivation)
    if not candidates:
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="no_source",
            message="no candidate URLs from pdf/url/arxiv fields",
            target_path=str(target_path),
        )
        record_checkpoint(outcome)
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    if options.dry_run:
        outcome = EntryOutcome(
            bib_file=str(bib_file),
            key=key,
            status="dry_run",
            message=f"would try {len(candidates)} URL(s)",
            url=candidates[0],
            target_path=str(target_path),
        )
        record_checkpoint(outcome)
        progress.emit(dataclasses.asdict(outcome))
        return outcome

    last_error = ""
    total_attempts = 0
    for candidate in candidates:
        result = download_pdf(
            session,
            cadence,
            candidate,
            target_path,
            options,
            attempt_logger=emit_download_event,
        )
        total_attempts += result.attempts
        if result.ok:
            entry["file"] = format_file_field(target_path.resolve(), "pdf")
            if result.final_url and "pdf" not in entry:
                entry["pdf"] = result.final_url
            outcome = EntryOutcome(
                bib_file=str(bib_file),
                key=key,
                status="downloaded",
                message="downloaded and linked",
                url=result.final_url or candidate,
                target_path=str(target_path),
                attempts=total_attempts,
                bytes_written=result.bytes_written,
            )
            maybe_set_pdf_field(entry, result.final_url or candidate, dry_run=options.dry_run)
            record_checkpoint(outcome)
            progress.emit(dataclasses.asdict(outcome))
            return outcome

        last_error = f"{candidate} -> {result.message}"

    fallback_candidates = supplemental_open_access_candidates(
        entry=entry,
        session=session,
        options=options,
        cache=oa_lookup_cache,
    )
    if fallback_candidates:
        seen = {canonicalize_url(u) for u in candidates}
        for candidate in fallback_candidates:
            if canonicalize_url(candidate) in seen:
                continue
            result = download_pdf(
                session,
                cadence,
                candidate,
                target_path,
                options,
                attempt_logger=emit_download_event,
            )
            total_attempts += result.attempts
            if result.ok:
                entry["file"] = format_file_field(target_path.resolve(), "pdf")
                maybe_set_pdf_field(entry, result.final_url or candidate, dry_run=options.dry_run)
                outcome = EntryOutcome(
                    bib_file=str(bib_file),
                    key=key,
                    status="downloaded",
                    message="downloaded and linked",
                    url=result.final_url or candidate,
                    target_path=str(target_path),
                    attempts=total_attempts,
                    bytes_written=result.bytes_written,
                )
                record_checkpoint(outcome)
                progress.emit(dataclasses.asdict(outcome))
                return outcome
            last_error = f"{candidate} -> {result.message}"

    outcome = EntryOutcome(
        bib_file=str(bib_file),
        key=key,
        status="failed",
        message=last_error or "download failed",
        target_path=str(target_path),
        attempts=total_attempts,
    )
    record_checkpoint(outcome)
    progress.emit(dataclasses.asdict(outcome))
    return outcome


def run_pdf_sync(options: PdfSyncOptions) -> PdfSyncResult:
    options = dataclasses.replace(options)
    cli_host_overrides = {
        normalize_host(k): max(0.0, float(v))
        for k, v in options.host_min_interval_seconds_by_host.items()
    }
    options.host_min_interval_seconds_by_host = default_host_intervals()
    options = apply_policy_overrides(options)
    options.host_min_interval_seconds_by_host.update(cli_host_overrides)

    files, unresolved = expand_targets(options.targets)
    summary: dict[str, int | str] = {
        "files_total": len(files),
        "files_modified": 0,
        "parse_errors": 0,
        "entries_total": 0,
        "entries_processed": 0,
        "entries_modified": 0,
        "downloaded": 0,
        "linked_existing": 0,
        "already_present": 0,
        "no_source": 0,
        "dry_run": 0,
        "failed": 0,
        "resumed_skip": 0,
        "no_download": 0,
        "unresolved_targets": len(unresolved),
        "aborted": 0,
    }
    failures: list[EntryOutcome] = []

    checkpoint: CheckpointStore | None = None
    if options.checkpoint_path:
        checkpoint = CheckpointStore(options.checkpoint_path)
        checkpoint.load()
    last_checkpoint_save_at = time.monotonic()

    progress = ProgressLogger(options.progress_log, console_progress=options.console_progress)
    if unresolved:
        for raw in unresolved:
            progress.emit({"status": "unresolved_target", "target": raw})

    cadence = HostCadenceController(
        default_interval=options.host_default_min_interval_seconds,
        per_host=options.host_min_interval_seconds_by_host,
        jitter_seconds=options.backoff_jitter_seconds,
    )
    session = build_http_session(options.user_agent)
    oa_lookup_cache: dict[str, list[str]] = {}

    consecutive_failures = 0

    try:
        for bib_file in files:
            try:
                bib_db = parse_bib(bib_file)
            except Exception as ex:
                summary["parse_errors"] = int(summary["parse_errors"]) + 1
                failure = EntryOutcome(
                    bib_file=str(bib_file),
                    key="*",
                    status="failed",
                    message=f"parse error: {ex}",
                )
                failures.append(failure)
                progress.emit(dataclasses.asdict(failure))
                if checkpoint:
                    checkpoint.save()
                continue

            entries = bib_db.entries
            summary["entries_total"] = int(summary["entries_total"]) + len(entries)

            file_changed = False

            for idx, entry in enumerate(entries, start=1):
                if options.max_entries and idx > options.max_entries:
                    break

                summary["entries_processed"] = int(summary["entries_processed"]) + 1
                before_entry = json.dumps(entry, sort_keys=True)
                outcome = process_entry(
                    entry=entry,
                    bib_file=bib_file,
                    options=options,
                    session=session,
                    cadence=cadence,
                    checkpoint=checkpoint,
                    progress=progress,
                    oa_lookup_cache=oa_lookup_cache,
                )
                after_entry = json.dumps(entry, sort_keys=True)
                entry_changed = before_entry != after_entry

                status = outcome.status
                summary[status] = int(summary.get(status, 0)) + 1

                if entry_changed and not options.dry_run:
                    file_changed = True
                    summary["entries_modified"] = int(summary["entries_modified"]) + 1

                if status == "failed":
                    failures.append(outcome)
                    if counts_toward_abort_budget(outcome):
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0
                elif status != "resumed_skip":
                    consecutive_failures = 0

                if options.max_consecutive_failures > 0 and consecutive_failures >= options.max_consecutive_failures:
                    summary["aborted"] = 1
                    progress.emit(
                        {
                            "status": "aborted",
                            "reason": "max_consecutive_failures_reached",
                            "count": consecutive_failures,
                        }
                    )
                    break

                if checkpoint and not options.dry_run:
                    flush_seconds = max(0.0, options.checkpoint_flush_seconds)
                    now = time.monotonic()
                    if flush_seconds == 0.0 or (now - last_checkpoint_save_at) >= flush_seconds:
                        checkpoint.save()
                        last_checkpoint_save_at = now

            if file_changed and not options.dry_run:
                backup = bib_file.with_suffix(bib_file.suffix + ".backup")
                shutil.copy2(bib_file, backup)
                write_bib(bib_file, bib_db)
                summary["files_modified"] = int(summary["files_modified"]) + 1

            if checkpoint:
                checkpoint.save()
                last_checkpoint_save_at = time.monotonic()

            if int(summary["aborted"]) == 1:
                break
    finally:
        session.close()

    if checkpoint and not options.dry_run:
        checkpoint.save(force=True)

    summary["failed"] = len(failures)
    return PdfSyncResult(summary=summary, failures=failures)
