#!/usr/bin/env python3
"""
Enrich BibTeX entries with arXiv metadata.

This script adds:
  - eprint = {<arxiv_id>}
  - archiveprefix = {arXiv}
  - primaryclass = {<arxiv_primary_category>}    (when available)
  - arxiv = {https://arxiv.org/abs/<arxiv_id>}

It intentionally does NOT modify existing url/pdf fields so canonical venue URLs
such as OpenReview or PMLR remain untouched.

Matching strategy:
1) OpenAlex lookup by title (preferred when arXiv ID is present)
2) arXiv API lookup by title + first-author surname
3) Confidence gating using title similarity + author/year checks
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import hashlib
import json
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import bibtexparser
import requests
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_API_URL = "https://export.arxiv.org/api/query"

DEFAULT_CACHE_PATH = Path("ops/arxiv-lookup-cache.json")
DEFAULT_REPORT_PATH = Path("ops/arxiv-enrichment-report.jsonl")
DEFAULT_CHECKPOINT_PATH = Path("ops/arxiv-enrichment-checkpoint.json")
DEFAULT_TRIAGE_DIR = Path("ops/unresolved")

MAX_TITLE_QUERY_CHARS = 256
MAX_ARXIV_RESULTS = 12
MAX_OPENALEX_RESULTS = 15
ARXIV_MIN_INTERVAL_DEFAULT = 3.0
OPENALEX_MIN_INTERVAL_DEFAULT = 0.1  # 10 rps default; conservative across OpenAlex docs variants.

_LAST_ARXIV_REQUEST_TS = 0.0
_LAST_OPENALEX_REQUEST_TS = 0.0


@dataclasses.dataclass
class Candidate:
    arxiv_id: str
    abs_url: str
    pdf_url: str
    title: str
    authors: list[str]
    year: int | None
    primary_class: str | None
    source: str
    source_rank: int
    source_ref: str


@dataclasses.dataclass
class MatchResult:
    candidate: Candidate
    title_score: float
    author_score: float
    year_score: float
    confidence: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich BibTeX entries with arXiv metadata using OpenAlex + arXiv API"
    )
    parser.add_argument("files", nargs="+", help="BibTeX files or glob patterns")
    parser.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE_PATH),
        help=f"Lookup cache path (default: {DEFAULT_CACHE_PATH})",
    )
    parser.add_argument(
        "--checkpoint",
        default=str(DEFAULT_CHECKPOINT_PATH),
        help=f"Checkpoint path for resumable runs (default: {DEFAULT_CHECKPOINT_PATH})",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Unresolved/ambiguous report JSONL path (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--triage-dir",
        default=str(DEFAULT_TRIAGE_DIR),
        help=f"Triage queue directory for unresolved entries (default: {DEFAULT_TRIAGE_DIR})",
    )
    parser.add_argument(
        "--triage-prefix",
        default="arxiv",
        help="Prefix used for triage queue files (default: arxiv)",
    )
    parser.add_argument(
        "--no-triage",
        action="store_true",
        help="Disable unresolved triage queue output files",
    )
    parser.add_argument(
        "--mailto",
        default="",
        help="Email for OpenAlex polite pool (recommended)",
    )
    parser.add_argument(
        "--openalex-api-key",
        default=os.environ.get("OPENALEX_API_KEY", ""),
        help="OpenAlex API key (or set OPENALEX_API_KEY env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute matches but do not write file changes",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing arXiv fields if present",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=0,
        help="Process at most N entries per file (0 = all)",
    )
    parser.add_argument(
        "--min-title-score",
        type=float,
        default=0.92,
        help="Minimum normalized title similarity for acceptance (default: 0.92)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.90,
        help="Minimum overall confidence for acceptance (default: 0.90)",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Sleep between API requests in milliseconds (default: 80)",
    )
    parser.add_argument(
        "--arxiv-min-interval",
        type=float,
        default=ARXIV_MIN_INTERVAL_DEFAULT,
        help="Minimum seconds between arXiv API requests (default: 3.0)",
    )
    parser.add_argument(
        "--openalex-min-interval",
        type=float,
        default=OPENALEX_MIN_INTERVAL_DEFAULT,
        help="Minimum seconds between OpenAlex requests (default: 0.1)",
    )
    parser.add_argument(
        "--save-cache-every",
        type=int,
        default=25,
        help="Persist lookup cache every N processed entries (default: 25)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=25,
        help="Persist checkpoint every N processed entries (default: 25)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoint state and process from scratch",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Delete existing checkpoint file before processing",
    )
    parser.add_argument(
        "--start-key",
        default="",
        help="Skip entries until this BibTeX key is reached (per file)",
    )
    parser.add_argument(
        "--entry-timeout",
        type=float,
        default=45.0,
        help="Soft per-entry timeout in seconds (default: 45.0, 0 disables)",
    )
    parser.add_argument(
        "--http-connect-timeout",
        type=float,
        default=8.0,
        help="HTTP connect timeout seconds (default: 8.0)",
    )
    parser.add_argument(
        "--http-read-timeout",
        type=float,
        default=20.0,
        help="HTTP read timeout seconds (default: 20.0)",
    )
    parser.add_argument(
        "--http-max-retries",
        type=int,
        default=2,
        help="HTTP retry attempts for transient failures (default: 2)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-entry matching details",
    )
    return parser.parse_args()


def make_session(max_retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max(0, int(max_retries)),
        connect=max(0, int(max_retries)),
        read=max(0, int(max_retries)),
        backoff_factor=0.2,
        backoff_max=4,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "bibliography-enrich-arxiv/1.0"})
    return session


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "openalex": {}, "arxiv": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "openalex": {}, "arxiv": {}}
    if not isinstance(data, dict):
        return {"version": 1, "openalex": {}, "arxiv": {}}
    data.setdefault("version", 1)
    data.setdefault("openalex", {})
    data.setdefault("arxiv", {})
    return data


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "files": {}}
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    data.setdefault("version", 1)
    data.setdefault("files", {})
    return data


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def strip_latex(s: str) -> str:
    if not s:
        return ""
    out = s
    out = out.replace("\\textasciicircum{}", "^")
    out = out.replace("\\textasciicircum", "^")
    out = out.replace("\\&", "&")
    out = out.replace("$", "")
    out = out.replace("{", "").replace("}", "")
    # Remove common LaTeX commands while preserving arguments.
    out = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", out)
    out = out.replace("\\", " ")
    return normalize_spaces(out)


def normalize_title(s: str) -> str:
    s = strip_latex(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return normalize_spaces(s)


def tokenize_title(s: str) -> set[str]:
    return {t for t in normalize_title(s).split(" ") if t}


def title_similarity(a: str, b: str) -> float:
    na = normalize_title(a)
    nb = normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(a=na, b=nb).ratio()
    ta = tokenize_title(na)
    tb = tokenize_title(nb)
    if not ta or not tb:
        return seq
    jac = len(ta & tb) / len(ta | tb)
    return max(seq, 0.65 * seq + 0.35 * jac)


def parse_year(value: str | int | None) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"(19|20)\d{2}", s)
    if not m:
        return None
    return int(m.group(0))


def parse_authors(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(" and ") if p.strip()]
    return [normalize_spaces(strip_latex(p)) for p in parts]


def surname(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    if not text:
        return ""
    if "," in text:
        left = text.split(",", 1)[0].strip()
        tokens = re.findall(r"[a-z0-9]+", left)
        return tokens[-1] if tokens else ""
    tokens = re.findall(r"[a-z0-9]+", text)
    return tokens[-1] if tokens else ""


def first_author_surname(entry: dict[str, Any]) -> str:
    authors = parse_authors(str(entry.get("author", "")))
    if not authors:
        return ""
    return surname(authors[0])


def extract_arxiv_id(text: str) -> str:
    if not text:
        return ""
    # Handles modern IDs and old category IDs, optionally with version suffix.
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([A-Za-z\-\.]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?", text, re.IGNORECASE)
    if not m:
        m = re.search(r"\b([A-Za-z\-\.]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?\b", text)
        if not m:
            return ""
    return m.group(1)


def candidate_from_openalex(item: dict[str, Any], rank: int) -> Candidate | None:
    ids = item.get("ids") or {}
    arxiv_url = str(ids.get("arxiv") or "").strip()
    arxiv_id = extract_arxiv_id(arxiv_url)
    if not arxiv_id:
        for loc in item.get("locations") or []:
            for field in ("landing_page_url", "pdf_url"):
                maybe = str((loc or {}).get(field) or "")
                arxiv_id = extract_arxiv_id(maybe)
                if arxiv_id:
                    break
            if arxiv_id:
                break
    if not arxiv_id:
        return None

    title = str(item.get("title") or item.get("display_name") or "").strip()
    year = parse_year(item.get("publication_year"))
    authors = [
        str(((a or {}).get("author") or {}).get("display_name") or "").strip()
        for a in (item.get("authorships") or [])
        if ((a or {}).get("author") or {}).get("display_name")
    ]
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    source_ref = str(item.get("id") or "")
    return Candidate(
        arxiv_id=arxiv_id,
        abs_url=abs_url,
        pdf_url=pdf_url,
        title=title,
        authors=authors,
        year=year,
        primary_class=None,
        source="openalex",
        source_rank=rank,
        source_ref=source_ref,
    )


def query_openalex(
    session: requests.Session,
    cache: dict[str, Any],
    title: str,
    mailto: str,
    openalex_api_key: str,
    openalex_min_interval: float,
    sleep_ms: int,
    connect_timeout: float,
    read_timeout: float,
) -> list[Candidate]:
    norm_key = hashlib.sha1(normalize_title(title).encode("utf-8")).hexdigest()
    cached = cache["openalex"].get(norm_key)
    if isinstance(cached, list):
        return [Candidate(**row) for row in cached]

    params = {
        "search": title[:MAX_TITLE_QUERY_CHARS],
        "per-page": MAX_OPENALEX_RESULTS,
    }
    if mailto:
        params["mailto"] = mailto
    if openalex_api_key:
        params["api_key"] = openalex_api_key

    candidates: list[Candidate] = []
    try:
        throttle_openalex(openalex_min_interval)
        resp = session.get(
            OPENALEX_WORKS_URL,
            params=params,
            timeout=(max(1.0, connect_timeout), max(1.0, read_timeout)),
        )
        if resp.status_code == 429:
            # Avoid long apparent hangs from server-directed retry windows.
            return []
        if resp.ok:
            payload = resp.json()
            for idx, item in enumerate(payload.get("results") or []):
                cand = candidate_from_openalex(item, rank=idx)
                if cand is not None:
                    candidates.append(cand)
    except Exception:
        candidates = []

    cache["openalex"][norm_key] = [dataclasses.asdict(c) for c in candidates]
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return candidates


def parse_arxiv_feed(xml_text: str) -> list[Candidate]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    out: list[Candidate] = []
    for idx, entry in enumerate(root.findall("atom:entry", ns)):
        abs_url = normalize_spaces(entry.findtext("atom:id", default="", namespaces=ns))
        arxiv_id = extract_arxiv_id(abs_url)
        if not arxiv_id:
            continue
        title = normalize_spaces(entry.findtext("atom:title", default="", namespaces=ns))
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = parse_year(published)
        authors = [
            normalize_spaces(a.findtext("atom:name", default="", namespaces=ns))
            for a in entry.findall("atom:author", ns)
        ]
        primary = None
        cat = entry.find("arxiv:primary_category", ns)
        if cat is not None:
            primary = cat.attrib.get("term")

        out.append(
            Candidate(
                arxiv_id=arxiv_id,
                abs_url=f"https://arxiv.org/abs/{arxiv_id}",
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                title=title,
                authors=authors,
                year=year,
                primary_class=primary,
                source="arxiv",
                source_rank=idx,
                source_ref=abs_url,
            )
        )
    return out


def query_arxiv(
    session: requests.Session,
    cache: dict[str, Any],
    title: str,
    author_surname: str,
    sleep_ms: int,
    arxiv_min_interval: float,
    connect_timeout: float,
    read_timeout: float,
) -> list[Candidate]:
    norm_key = hashlib.sha1((normalize_title(title) + "|" + author_surname).encode("utf-8")).hexdigest()
    cached = cache["arxiv"].get(norm_key)
    if isinstance(cached, list):
        return [Candidate(**row) for row in cached]

    title_q = title[:MAX_TITLE_QUERY_CHARS]
    if author_surname:
        query = f'ti:"{title_q}" AND au:{author_surname}'
    else:
        query = f'ti:"{title_q}"'

    params = {
        "search_query": query,
        "start": 0,
        "max_results": MAX_ARXIV_RESULTS,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    candidates: list[Candidate] = []
    try:
        throttle_arxiv(arxiv_min_interval)
        resp = session.get(
            ARXIV_API_URL,
            params=params,
            timeout=(max(1.0, connect_timeout), max(1.0, read_timeout)),
        )
        if resp.ok:
            candidates = parse_arxiv_feed(resp.text)
    except Exception:
        candidates = []

    cache["arxiv"][norm_key] = [dataclasses.asdict(c) for c in candidates]
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return candidates


def throttle_arxiv(min_interval_seconds: float) -> None:
    """Respect arXiv legacy API terms: <= 1 request every 3 seconds."""
    global _LAST_ARXIV_REQUEST_TS
    min_interval_seconds = max(0.0, float(min_interval_seconds))
    now = time.monotonic()
    elapsed = now - _LAST_ARXIV_REQUEST_TS
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _LAST_ARXIV_REQUEST_TS = time.monotonic()


def throttle_openalex(min_interval_seconds: float) -> None:
    """Throttle OpenAlex request cadence to remain under configured request rate."""
    global _LAST_OPENALEX_REQUEST_TS
    min_interval_seconds = max(0.0, float(min_interval_seconds))
    now = time.monotonic()
    elapsed = now - _LAST_OPENALEX_REQUEST_TS
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _LAST_OPENALEX_REQUEST_TS = time.monotonic()


def candidate_year_score(entry_year: int | None, cand_year: int | None) -> float:
    if entry_year is None or cand_year is None:
        return 0.5
    delta = abs(entry_year - cand_year)
    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.95
    if delta == 2:
        return 0.6
    return 0.1


def candidate_author_score(first_surname: str, cand_authors: list[str]) -> float:
    if not first_surname:
        return 0.5
    if not cand_authors:
        return 0.4
    cand_surnames = {surname(a) for a in cand_authors if surname(a)}
    if first_surname in cand_surnames:
        return 1.0
    return 0.0


def compute_match(entry: dict[str, Any], cand: Candidate) -> MatchResult:
    etitle = str(entry.get("title", ""))
    eyear = parse_year(entry.get("year"))
    first_sname = first_author_surname(entry)

    tscore = title_similarity(etitle, cand.title)
    ascore = candidate_author_score(first_sname, cand.authors)
    yscore = candidate_year_score(eyear, cand.year)

    # Weighted confidence; source boost favors OpenAlex-derived arXiv IDs slightly.
    conf = 0.72 * tscore + 0.18 * ascore + 0.10 * yscore
    if cand.source == "openalex":
        conf = min(1.0, conf + 0.03)

    return MatchResult(
        candidate=cand,
        title_score=tscore,
        author_score=ascore,
        year_score=yscore,
        confidence=conf,
    )


def pick_best_match(
    entry: dict[str, Any],
    candidates: list[Candidate],
    min_title_score: float,
    min_confidence: float,
) -> MatchResult | None:
    if not candidates:
        return None
    ranked = sorted(
        (compute_match(entry, c) for c in candidates),
        key=lambda m: (m.confidence, m.title_score, -m.candidate.source_rank),
        reverse=True,
    )
    top = ranked[0]
    if top.title_score < min_title_score:
        return None
    if top.confidence < min_confidence:
        return None
    return top


def has_arxiv_fields(entry: dict[str, Any]) -> bool:
    eprint = str(entry.get("eprint", "")).strip()
    apfx = str(entry.get("archiveprefix", "")).strip().lower()
    arxiv = str(entry.get("arxiv", "")).strip()
    if eprint and apfx == "arxiv":
        return True
    if arxiv and "arxiv.org/abs/" in arxiv.lower():
        return True
    return False


def set_arxiv_fields(entry: dict[str, Any], match: MatchResult) -> None:
    cand = match.candidate
    entry["eprint"] = cand.arxiv_id
    entry["archiveprefix"] = "arXiv"
    entry["arxiv"] = cand.abs_url
    if cand.primary_class:
        entry["primaryclass"] = cand.primary_class


def load_bib(path: Path):
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    with path.open("r", encoding="utf-8") as f:
        return bibtexparser.load(f, parser=parser)


def write_bib(path: Path, bib_db: Any) -> None:
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.align_values = False
    path.write_text(writer.write(bib_db), encoding="utf-8")


def iter_file_paths(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for pat in patterns:
        matches = [Path(m) for m in sorted(glob.glob(pat, recursive=True))]
        if not matches:
            p = Path(pat)
            if p.exists():
                matches = [p]
        for p in matches:
            if p.is_file() and p.suffix.lower() == ".bib":
                rp = p.resolve()
                if rp not in seen:
                    out.append(p)
                    seen.add(rp)
    return out


def append_report(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def append_triage(
    triage_dir: Path,
    triage_prefix: str,
    triage_reason: str,
    payload: dict[str, Any],
) -> None:
    triage_dir.mkdir(parents=True, exist_ok=True)
    triage_path = triage_dir / f"{triage_prefix}-{triage_reason}.jsonl"
    with triage_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def has_non_arxiv_preprint_link(entry: dict[str, Any]) -> bool:
    non_arxiv_hosts = (
        "biorxiv.org",
        "medrxiv.org",
        "ssrn.com",
        "researchsquare.com",
        "osf.io",
    )
    for field in ("url", "pdf", "doi"):
        value = str(entry.get(field, "")).lower()
        if any(host in value for host in non_arxiv_hosts):
            return True
    return False


def classify_triage_reason(unresolved_payload: dict[str, Any]) -> str:
    reason = str(unresolved_payload.get("reason", ""))
    if reason == "missing_key_or_title":
        return "invalid_entry_metadata"
    if reason.startswith("entry_timeout"):
        return "query_timeout"
    if reason != "no_confident_match":
        return "other"

    if unresolved_payload.get("non_arxiv_preprint"):
        return "non_arxiv_preprint"

    top = unresolved_payload.get("top_candidates") or []
    if not top:
        return "no_arxiv_found"

    first = top[0] if isinstance(top[0], dict) else {}
    title_score = float(first.get("title_score", 0.0) or 0.0)
    confidence = float(first.get("confidence", 0.0) or 0.0)
    if title_score >= 0.80 or confidence >= 0.70:
        return "ambiguous_match"
    return "weak_candidate_match"


def process_file(
    path: Path,
    session: requests.Session,
    cache: dict[str, Any],
    cache_path: Path,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    args: argparse.Namespace,
    triage_counts: dict[str, int],
) -> tuple[int, int, int, int, bool]:
    db = load_bib(path)
    entries = list(db.entries)
    file_key = str(path)
    file_states = checkpoint.setdefault("files", {})
    prior = file_states.get(file_key, {}) if not args.no_resume else {}

    processed = int(prior.get("processed", 0))
    changed = int(prior.get("changed", 0))
    skipped_existing = int(prior.get("skipped_existing", 0))
    unresolved = int(prior.get("unresolved", 0))
    processed_keys = set(prior.get("processed_keys", []))
    completed = bool(prior.get("completed", False))
    processed_this_run = 0
    changed_this_run = 0

    if args.max_entries > 0:
        entries = entries[: args.max_entries]

    if completed and not args.no_resume:
        print(
            f"processing file: {path} ({len(entries)} entries) "
            f"[resume: already complete, skipping]"
        )
        return processed, changed, skipped_existing, unresolved, False

    print(f"processing file: {path} ({len(entries)} entries)")

    def persist_state(mark_completed: bool = False) -> None:
        file_states[file_key] = {
            "processed": processed,
            "changed": changed,
            "skipped_existing": skipped_existing,
            "unresolved": unresolved,
            "processed_keys": sorted(processed_keys),
            "completed": bool(mark_completed),
        }
        save_checkpoint(checkpoint_path, checkpoint)

    def emit_unresolved(unresolved_payload: dict[str, Any]) -> None:
        append_report(Path(args.report), unresolved_payload)
        if args.no_triage:
            return
        triage_reason = classify_triage_reason(unresolved_payload)
        triage_counts[triage_reason] = triage_counts.get(triage_reason, 0) + 1
        triage_payload = dict(unresolved_payload)
        triage_payload["triage_reason"] = triage_reason
        append_triage(
            triage_dir=Path(args.triage_dir),
            triage_prefix=args.triage_prefix,
            triage_reason=triage_reason,
            payload=triage_payload,
        )

    start_reached = not args.start_key or args.start_key in processed_keys
    saw_start_key = start_reached

    for entry in entries:
        key = str(entry.get("ID", ""))
        title = normalize_spaces(str(entry.get("title", "")))

        if key and key in processed_keys:
            continue

        if args.start_key and not start_reached:
            if key == args.start_key:
                start_reached = True
                saw_start_key = True
            else:
                continue

        entry_started = time.monotonic()

        def entry_timed_out() -> bool:
            if args.entry_timeout <= 0:
                return False
            return (time.monotonic() - entry_started) > float(args.entry_timeout)

        if not key or not title:
            unresolved += 1
            emit_unresolved(
                {
                    "file": str(path),
                    "entry_key": key,
                    "reason": "missing_key_or_title",
                }
            )
            if key:
                processed_keys.add(key)
            processed += 1
            processed_this_run += 1
            continue

        processed += 1
        processed_this_run += 1
        if processed % 25 == 0:
            print(
                f"  progress {path.name}: processed={processed} changed={changed} "
                f"skipped_existing={skipped_existing} unresolved={unresolved}"
            )
        if args.save_cache_every > 0 and processed % args.save_cache_every == 0:
            save_cache(cache_path, cache)
        if args.checkpoint_every > 0 and processed_this_run % args.checkpoint_every == 0:
            persist_state(mark_completed=False)

        if has_arxiv_fields(entry) and not args.overwrite:
            skipped_existing += 1
            processed_keys.add(key)
            continue

        if entry_timed_out():
            unresolved += 1
            emit_unresolved(
                {
                    "file": str(path),
                    "entry_key": key,
                    "reason": "entry_timeout_before_lookup",
                    "title": title,
                }
            )
            processed_keys.add(key)
            continue

        first_sname = first_author_surname(entry)
        openalex = query_openalex(
            session=session,
            cache=cache,
            title=title,
            mailto=args.mailto,
            openalex_api_key=args.openalex_api_key,
            openalex_min_interval=args.openalex_min_interval,
            sleep_ms=args.sleep_ms,
            connect_timeout=args.http_connect_timeout,
            read_timeout=args.http_read_timeout,
        )
        match = pick_best_match(
            entry=entry,
            candidates=openalex,
            min_title_score=args.min_title_score,
            min_confidence=args.min_confidence,
        )
        if match is None:
            if entry_timed_out():
                unresolved += 1
                emit_unresolved(
                    {
                        "file": str(path),
                        "entry_key": key,
                        "reason": "entry_timeout_after_openalex",
                        "title": title,
                    }
                )
                processed_keys.add(key)
                continue

            arxiv = query_arxiv(
                session=session,
                cache=cache,
                title=title,
                author_surname=first_sname,
                sleep_ms=args.sleep_ms,
                arxiv_min_interval=args.arxiv_min_interval,
                connect_timeout=args.http_connect_timeout,
                read_timeout=args.http_read_timeout,
            )
            candidates = openalex + arxiv
            match = pick_best_match(
                entry=entry,
                candidates=candidates,
                min_title_score=args.min_title_score,
                min_confidence=args.min_confidence,
            )
        else:
            candidates = openalex
        if match is None:
            unresolved += 1
            top_candidates = sorted(
                (compute_match(entry, c) for c in candidates),
                key=lambda m: (m.confidence, m.title_score),
                reverse=True,
            )[:3]
            emit_unresolved(
                {
                    "file": str(path),
                    "entry_key": key,
                    "reason": "no_confident_match",
                    "title": title,
                    "non_arxiv_preprint": has_non_arxiv_preprint_link(entry),
                    "top_candidates": [
                        {
                            "source": m.candidate.source,
                            "arxiv_id": m.candidate.arxiv_id,
                            "title": m.candidate.title,
                            "confidence": round(m.confidence, 4),
                            "title_score": round(m.title_score, 4),
                            "author_score": round(m.author_score, 4),
                            "year_score": round(m.year_score, 4),
                        }
                        for m in top_candidates
                    ],
                }
            )
            processed_keys.add(key)
            continue

        if args.verbose:
            print(
                f"[match] {path}::{key} -> {match.candidate.arxiv_id} "
                f"(src={match.candidate.source}, conf={match.confidence:.3f}, "
                f"title={match.title_score:.3f}, author={match.author_score:.3f}, year={match.year_score:.3f})"
            )

        set_arxiv_fields(entry, match)
        changed += 1
        changed_this_run += 1
        processed_keys.add(key)

    # If max_entries is set, we only mutated a prefix in memory. Do not write partial file in non-dry mode.
    if changed_this_run > 0 and not args.dry_run and args.max_entries == 0:
        write_bib(path, db)

    mark_completed = bool(args.max_entries == 0 and not args.start_key)
    start_key_missing = bool(args.start_key and not saw_start_key)
    if args.start_key and not saw_start_key:
        print(f"  start key `{args.start_key}` not found in {path.name}; file left incomplete in checkpoint")
    persist_state(mark_completed=mark_completed)

    return processed, changed, skipped_existing, unresolved, start_key_missing


def main() -> int:
    args = parse_args()
    paths = iter_file_paths(args.files)
    if not paths:
        print("No BibTeX files matched.")
        return 1

    # Reset report for this run.
    report_path = Path(args.report)
    if report_path.exists():
        report_path.unlink()

    checkpoint_path = Path(args.checkpoint)
    if args.reset_checkpoint and checkpoint_path.exists():
        checkpoint_path.unlink()

    triage_counts: dict[str, int] = {}
    triage_summary_path = Path(args.triage_dir) / f"{args.triage_prefix}-summary.json"
    if not args.no_triage:
        triage_dir = Path(args.triage_dir)
        triage_dir.mkdir(parents=True, exist_ok=True)
        for old in triage_dir.glob(f"{args.triage_prefix}-*.jsonl"):
            old.unlink()
        if triage_summary_path.exists():
            triage_summary_path.unlink()

    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    checkpoint = load_checkpoint(checkpoint_path)
    session = make_session(max_retries=args.http_max_retries)

    total_processed = 0
    total_changed = 0
    total_skipped = 0
    total_unresolved = 0
    start_key_misses = 0

    try:
        for p in paths:
            processed, changed, skipped_existing, unresolved, start_key_missing = process_file(
                path=p,
                session=session,
                cache=cache,
                cache_path=cache_path,
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                args=args,
                triage_counts=triage_counts,
            )
            total_processed += processed
            total_changed += changed
            total_skipped += skipped_existing
            total_unresolved += unresolved
            if start_key_missing:
                start_key_misses += 1
            print(
                f"{p}: processed={processed} changed={changed} "
                f"skipped_existing={skipped_existing} unresolved={unresolved}"
            )
            save_cache(cache_path, cache)
            save_checkpoint(checkpoint_path, checkpoint)
    except KeyboardInterrupt:
        save_cache(cache_path, cache)
        save_checkpoint(checkpoint_path, checkpoint)
        if not args.no_triage:
            triage_summary_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "counts": triage_counts,
                        "total_unresolved": total_unresolved,
                        "report_path": str(report_path),
                        "interrupted": True,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        print("\nInterrupted. Progress cached.")
        return 130

    save_cache(cache_path, cache)
    save_checkpoint(checkpoint_path, checkpoint)
    if not args.no_triage:
        triage_summary_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "counts": triage_counts,
                    "total_unresolved": total_unresolved,
                    "report_path": str(report_path),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    print("\nSummary:")
    print(f"  files: {len(paths)}")
    print(f"  processed_entries: {total_processed}")
    print(f"  changed_entries: {total_changed}")
    print(f"  skipped_existing: {total_skipped}")
    print(f"  unresolved_entries: {total_unresolved}")
    print(f"  cache: {cache_path}")
    print(f"  checkpoint: {checkpoint_path}")
    print(f"  unresolved_report: {report_path}")
    if args.start_key:
        print(f"  start_key_misses: {start_key_misses}")
    if not args.no_triage:
        print(f"  triage_dir: {args.triage_dir}")
        print(f"  triage_summary: {triage_summary_path}")
    if args.dry_run:
        print("  mode: dry-run (no files written)")
    elif args.max_entries > 0:
        print("  mode: max-entries set; no files written to avoid partial updates")

    if args.start_key and start_key_misses > 0:
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
