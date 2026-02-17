#!/usr/bin/env python3
"""Enrich BibTeX entries with DOI metadata using Crossref and OpenAlex."""

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

import bibtexparser
import requests
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

DEFAULT_CACHE_PATH = Path("ops/doi-lookup-cache.json")
DEFAULT_REPORT_PATH = Path("ops/doi-enrichment-report.jsonl")

MAX_TITLE_QUERY_CHARS = 256
MAX_CROSSREF_RESULTS = 12
MAX_OPENALEX_RESULTS = 15

_LAST_CROSSREF_REQUEST_TS = 0.0
_LAST_OPENALEX_REQUEST_TS = 0.0

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


@dataclasses.dataclass
class Candidate:
    doi: str
    title: str
    authors: list[str]
    year: int | None
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
    p = argparse.ArgumentParser(description="Enrich BibTeX entries with DOI metadata")
    p.add_argument("files", nargs="+", help="BibTeX files or glob patterns")
    p.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE_PATH),
        help=f"Lookup cache path (default: {DEFAULT_CACHE_PATH})",
    )
    p.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Unresolved report path (default: {DEFAULT_REPORT_PATH})",
    )
    p.add_argument(
        "--mailto",
        default=os.environ.get("CROSSREF_MAILTO", ""),
        help="Email for polite pool (Crossref/OpenAlex)",
    )
    p.add_argument(
        "--openalex-api-key",
        default=os.environ.get("OPENALEX_API_KEY", ""),
        help="OpenAlex API key (or set OPENALEX_API_KEY)",
    )
    p.add_argument("--dry-run", action="store_true", help="Do not write file changes")
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing DOI fields",
    )
    p.add_argument(
        "--max-entries",
        type=int,
        default=0,
        help="Process at most N entries per file (0=all)",
    )
    p.add_argument(
        "--min-title-score",
        type=float,
        default=0.92,
        help="Minimum title similarity for acceptance (default: 0.92)",
    )
    p.add_argument(
        "--min-confidence",
        type=float,
        default=0.90,
        help="Minimum overall confidence for acceptance (default: 0.90)",
    )
    p.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Sleep between requests in milliseconds (default: 80)",
    )
    p.add_argument(
        "--crossref-min-interval",
        type=float,
        default=0.2,
        help="Minimum seconds between Crossref requests (default: 0.2)",
    )
    p.add_argument(
        "--openalex-min-interval",
        type=float,
        default=0.1,
        help="Minimum seconds between OpenAlex requests (default: 0.1)",
    )
    p.add_argument(
        "--save-cache-every",
        type=int,
        default=25,
        help="Persist cache every N processed entries (default: 25)",
    )
    p.add_argument("--verbose", action="store_true", help="Print per-entry match details")
    return p.parse_args()


def make_session(mailto: str) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
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

    user_agent = "bibliography-enrich-doi/1.0"
    if mailto:
        user_agent += f" (mailto:{mailto})"
    session.headers.update({"User-Agent": user_agent})
    return session


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "crossref": {}, "openalex": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "crossref": {}, "openalex": {}}
    if not isinstance(data, dict):
        return {"version": 1, "crossref": {}, "openalex": {}}
    data.setdefault("version", 1)
    data.setdefault("crossref", {})
    data.setdefault("openalex", {})
    return data


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def strip_latex(s: str) -> str:
    if not s:
        return ""
    out = s.replace("\\&", "&").replace("{", "").replace("}", "")
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
    m = re.search(r"(19|20)\d{2}", str(value).strip())
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
        tokens = re.findall(r"[a-z0-9]+", text.split(",", 1)[0])
        return tokens[-1] if tokens else ""
    tokens = re.findall(r"[a-z0-9]+", text)
    return tokens[-1] if tokens else ""


def first_author_surname(entry: dict[str, Any]) -> str:
    authors = parse_authors(str(entry.get("author", "")))
    if not authors:
        return ""
    return surname(authors[0])


def extract_doi(text: str) -> str:
    if not text:
        return ""
    m = DOI_RE.search(text)
    if not m:
        return ""
    doi = m.group(0)
    doi = doi.rstrip(".,;)")
    return doi.lower()


def normalize_doi(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.lower().startswith("https://doi.org/"):
        v = v[16:]
    elif v.lower().startswith("http://doi.org/"):
        v = v[15:]
    doi = extract_doi(v)
    return doi


def candidate_from_crossref(item: dict[str, Any], rank: int) -> Candidate | None:
    doi = normalize_doi(str(item.get("DOI") or ""))
    if not doi:
        return None

    titles = item.get("title") or []
    title = ""
    if isinstance(titles, list) and titles:
        title = str(titles[0])

    year = None
    for date_key in ("published-print", "published-online", "issued"):
        node = item.get(date_key) or {}
        parts = node.get("date-parts") or []
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            year = parse_year(parts[0][0])
            if year is not None:
                break

    authors = []
    for a in item.get("author") or []:
        given = str((a or {}).get("given") or "").strip()
        family = str((a or {}).get("family") or "").strip()
        full = normalize_spaces(f"{given} {family}".strip())
        if full:
            authors.append(full)

    return Candidate(
        doi=doi,
        title=title,
        authors=authors,
        year=year,
        source="crossref",
        source_rank=rank,
        source_ref=f"doi:{doi}",
    )


def candidate_from_openalex(item: dict[str, Any], rank: int) -> Candidate | None:
    ids = item.get("ids") or {}
    doi = normalize_doi(str(ids.get("doi") or ""))
    if not doi:
        doi = normalize_doi(str(item.get("doi") or ""))
    if not doi:
        return None

    title = str(item.get("title") or item.get("display_name") or "").strip()
    year = parse_year(item.get("publication_year"))
    authors = [
        str(((a or {}).get("author") or {}).get("display_name") or "").strip()
        for a in (item.get("authorships") or [])
        if ((a or {}).get("author") or {}).get("display_name")
    ]

    return Candidate(
        doi=doi,
        title=title,
        authors=authors,
        year=year,
        source="openalex",
        source_rank=rank,
        source_ref=str(item.get("id") or ""),
    )


def throttle_crossref(min_interval_seconds: float) -> None:
    global _LAST_CROSSREF_REQUEST_TS
    min_interval_seconds = max(0.0, float(min_interval_seconds))
    now = time.monotonic()
    elapsed = now - _LAST_CROSSREF_REQUEST_TS
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _LAST_CROSSREF_REQUEST_TS = time.monotonic()


def throttle_openalex(min_interval_seconds: float) -> None:
    global _LAST_OPENALEX_REQUEST_TS
    min_interval_seconds = max(0.0, float(min_interval_seconds))
    now = time.monotonic()
    elapsed = now - _LAST_OPENALEX_REQUEST_TS
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    _LAST_OPENALEX_REQUEST_TS = time.monotonic()


def query_crossref(
    session: requests.Session,
    cache: dict[str, Any],
    title: str,
    first_sname: str,
    crossref_min_interval: float,
    sleep_ms: int,
    mailto: str,
) -> list[Candidate]:
    key_seed = normalize_title(title) + "|" + first_sname
    norm_key = hashlib.sha1(key_seed.encode("utf-8")).hexdigest()
    cached = cache["crossref"].get(norm_key)
    if isinstance(cached, list):
        return [Candidate(**row) for row in cached]

    params = {
        "query.title": title[:MAX_TITLE_QUERY_CHARS],
        "rows": MAX_CROSSREF_RESULTS,
        "select": "DOI,title,author,published-print,published-online,issued",
    }
    if first_sname:
        params["query.author"] = first_sname
    if mailto:
        params["mailto"] = mailto

    out: list[Candidate] = []
    try:
        throttle_crossref(crossref_min_interval)
        resp = session.get(CROSSREF_WORKS_URL, params=params, timeout=(8, 20))
        if resp.status_code != 429 and resp.ok:
            data = resp.json()
            items = ((data.get("message") or {}).get("items") or [])
            for idx, item in enumerate(items):
                cand = candidate_from_crossref(item, rank=idx)
                if cand is not None:
                    out.append(cand)
    except Exception:
        out = []

    cache["crossref"][norm_key] = [dataclasses.asdict(c) for c in out]
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return out


def query_openalex(
    session: requests.Session,
    cache: dict[str, Any],
    title: str,
    mailto: str,
    openalex_api_key: str,
    openalex_min_interval: float,
    sleep_ms: int,
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

    out: list[Candidate] = []
    try:
        throttle_openalex(openalex_min_interval)
        resp = session.get(OPENALEX_WORKS_URL, params=params, timeout=(8, 20))
        if resp.status_code != 429 and resp.ok:
            data = resp.json()
            for idx, item in enumerate(data.get("results") or []):
                cand = candidate_from_openalex(item, rank=idx)
                if cand is not None:
                    out.append(cand)
    except Exception:
        out = []

    cache["openalex"][norm_key] = [dataclasses.asdict(c) for c in out]
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return out


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


def candidate_author_score(first_sname: str, cand_authors: list[str]) -> float:
    if not first_sname:
        return 0.5
    if not cand_authors:
        return 0.4
    cand_surnames = {surname(a) for a in cand_authors if surname(a)}
    return 1.0 if first_sname in cand_surnames else 0.0


def compute_match(entry: dict[str, Any], cand: Candidate) -> MatchResult:
    etitle = str(entry.get("title", ""))
    eyear = parse_year(entry.get("year"))
    first_sname = first_author_surname(entry)

    tscore = title_similarity(etitle, cand.title)
    ascore = candidate_author_score(first_sname, cand.authors)
    yscore = candidate_year_score(eyear, cand.year)

    conf = 0.72 * tscore + 0.18 * ascore + 0.10 * yscore
    if cand.source == "crossref":
        conf = min(1.0, conf + 0.02)

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


def has_doi_fields(entry: dict[str, Any]) -> bool:
    return bool(normalize_doi(str(entry.get("doi", ""))))


def set_doi_fields(entry: dict[str, Any], match: MatchResult) -> None:
    entry["doi"] = match.candidate.doi


def load_bib(path: Path) -> Any:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    with path.open("r", encoding="utf-8") as f:
        return bibtexparser.load(f, parser=parser)


def write_bib(path: Path, db: Any) -> None:
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.align_values = False
    path.write_text(writer.write(db), encoding="utf-8")


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


def process_file(
    path: Path,
    session: requests.Session,
    cache: dict[str, Any],
    cache_path: Path,
    args: argparse.Namespace,
) -> tuple[int, int, int, int]:
    db = load_bib(path)
    entries = db.entries
    changed = 0
    processed = 0
    skipped_existing = 0
    unresolved = 0

    if args.max_entries > 0:
        entries = entries[: args.max_entries]

    print(f"processing file: {path} ({len(entries)} entries)")

    for entry in entries:
        key = str(entry.get("ID", ""))
        title = normalize_spaces(str(entry.get("title", "")))
        if not key or not title:
            unresolved += 1
            append_report(
                Path(args.report),
                {
                    "file": str(path),
                    "entry_key": key,
                    "reason": "missing_key_or_title",
                },
            )
            continue

        processed += 1
        if processed % 25 == 0:
            print(
                f"  progress {path.name}: processed={processed} changed={changed} "
                f"skipped_existing={skipped_existing} unresolved={unresolved}"
            )
        if args.save_cache_every > 0 and processed % args.save_cache_every == 0:
            save_cache(cache_path, cache)

        if has_doi_fields(entry) and not args.overwrite:
            skipped_existing += 1
            continue

        first_sname = first_author_surname(entry)
        crossref = query_crossref(
            session=session,
            cache=cache,
            title=title,
            first_sname=first_sname,
            crossref_min_interval=args.crossref_min_interval,
            sleep_ms=args.sleep_ms,
            mailto=args.mailto,
        )
        match = pick_best_match(
            entry=entry,
            candidates=crossref,
            min_title_score=args.min_title_score,
            min_confidence=args.min_confidence,
        )

        if match is None:
            openalex = query_openalex(
                session=session,
                cache=cache,
                title=title,
                mailto=args.mailto,
                openalex_api_key=args.openalex_api_key,
                openalex_min_interval=args.openalex_min_interval,
                sleep_ms=args.sleep_ms,
            )
            candidates = crossref + openalex
            match = pick_best_match(
                entry=entry,
                candidates=candidates,
                min_title_score=args.min_title_score,
                min_confidence=args.min_confidence,
            )
        else:
            candidates = crossref

        if match is None:
            unresolved += 1
            top_candidates = sorted(
                (compute_match(entry, c) for c in candidates),
                key=lambda m: (m.confidence, m.title_score),
                reverse=True,
            )[:3]
            append_report(
                Path(args.report),
                {
                    "file": str(path),
                    "entry_key": key,
                    "reason": "no_confident_match",
                    "title": title,
                    "top_candidates": [
                        {
                            "source": m.candidate.source,
                            "doi": m.candidate.doi,
                            "title": m.candidate.title,
                            "confidence": round(m.confidence, 4),
                            "title_score": round(m.title_score, 4),
                            "author_score": round(m.author_score, 4),
                            "year_score": round(m.year_score, 4),
                        }
                        for m in top_candidates
                    ],
                },
            )
            continue

        if args.verbose:
            print(
                f"[match] {path}::{key} -> {match.candidate.doi} "
                f"(src={match.candidate.source}, conf={match.confidence:.3f}, "
                f"title={match.title_score:.3f}, author={match.author_score:.3f}, year={match.year_score:.3f})"
            )

        set_doi_fields(entry, match)
        changed += 1

    if changed > 0 and not args.dry_run and args.max_entries == 0:
        write_bib(path, db)

    return processed, changed, skipped_existing, unresolved


def main() -> int:
    args = parse_args()
    paths = iter_file_paths(args.files)
    if not paths:
        print("No BibTeX files matched.")
        return 1

    report_path = Path(args.report)
    if report_path.exists():
        report_path.unlink()

    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    session = make_session(mailto=args.mailto)

    total_processed = 0
    total_changed = 0
    total_skipped = 0
    total_unresolved = 0

    try:
        for p in paths:
            processed, changed, skipped_existing, unresolved = process_file(
                path=p,
                session=session,
                cache=cache,
                cache_path=cache_path,
                args=args,
            )
            total_processed += processed
            total_changed += changed
            total_skipped += skipped_existing
            total_unresolved += unresolved
            print(
                f"{p}: processed={processed} changed={changed} "
                f"skipped_existing={skipped_existing} unresolved={unresolved}"
            )
            save_cache(cache_path, cache)
    except KeyboardInterrupt:
        save_cache(cache_path, cache)
        print("\nInterrupted. Progress cached.")
        return 130

    save_cache(cache_path, cache)

    print("\nSummary:")
    print(f"  files: {len(paths)}")
    print(f"  processed_entries: {total_processed}")
    print(f"  changed_entries: {total_changed}")
    print(f"  skipped_existing: {total_skipped}")
    print(f"  unresolved_entries: {total_unresolved}")
    print(f"  cache: {cache_path}")
    print(f"  unresolved_report: {report_path}")
    if args.dry_run:
        print("  mode: dry-run (no files written)")
    elif args.max_entries > 0:
        print("  mode: max-entries set; no files written to avoid partial updates")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
