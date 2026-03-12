#!/usr/bin/env python3
"""Unified, repeatable operations CLI for this bibliography repository."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
import traceback
import unicodedata
import uuid
from pathlib import Path
from typing import Iterable

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode
from bibops_key_manager import KeyNormalizeOptions, result_to_json, run_key_normalize
from bibops_pdf_sync import PdfSyncOptions, parse_host_interval_overrides, run_pdf_sync
from core.bibmeta import validate_repo_bibmeta

DEFAULT_CONFIG_PATH = Path("ops/bibops.toml")
DEFAULT_DB_PATH = Path("bibliography.db")
LOCK_PATH = Path("ops/.bibops.lock")
ORALS_ROOT = Path("collections/orals")
CANONICAL_CONFERENCES_ROOT = Path("conferences")
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


@dataclasses.dataclass
class OpsConfig:
    roots: list[str]
    exclude_globs: list[str]
    db_path: str
    tracking_export: str
    issue_limit_per_type: int


@dataclasses.dataclass
class Issue:
    file_path: str
    entry_key: str | None
    issue_type: str
    severity: str
    message: str
    details: dict[str, str]


@dataclasses.dataclass
class FileResult:
    file_path: str
    parse_ok: bool
    entry_count: int
    error_message: str | None
    mtime: float
    size: int
    sha256: str


@dataclasses.dataclass
class EntryResult:
    file_path: str
    entry_key: str
    entry_type: str
    year: str
    title_norm: str
    doi_raw: str
    url_fp: str
    has_author: bool
    has_title: bool
    has_booktitle: bool
    author_raw: str
    has_url: bool
    has_pdf: bool
    has_file: bool


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_config() -> OpsConfig:
    return OpsConfig(
        roots=[
            "books",
            "conferences",
            "collections",
            "references",
            "courses",
            "theses",
            "presentations",
        ],
        exclude_globs=[
            "**/.git/**",
            "**/__pycache__/**",
            "**/*.backup",
            "**/*.bak",
            "collections/orals/**/*.bib",
        ],
        db_path=str(DEFAULT_DB_PATH),
        tracking_export="tracking.json",
        issue_limit_per_type=200,
    )


def load_config(path: Path) -> OpsConfig:
    cfg = default_config()
    if not path.exists():
        return cfg

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    roots = data.get("roots")
    exclude_globs = data.get("exclude_globs")
    db_path = data.get("db_path")
    tracking_export = data.get("tracking_export")
    issue_limit_per_type = data.get("issue_limit_per_type")

    if isinstance(roots, list) and all(isinstance(x, str) for x in roots):
        cfg.roots = roots
    if isinstance(exclude_globs, list) and all(isinstance(x, str) for x in exclude_globs):
        cfg.exclude_globs = exclude_globs
    if isinstance(db_path, str) and db_path:
        cfg.db_path = db_path
    if isinstance(tracking_export, str) and tracking_export:
        cfg.tracking_export = tracking_export
    if isinstance(issue_limit_per_type, int) and issue_limit_per_type > 0:
        cfg.issue_limit_per_type = issue_limit_per_type

    return cfg


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def norm_title(value: str) -> str:
    value = (value or "").replace("{", "").replace("}", "").strip()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value)


def norm_author(value: str) -> str:
    value = (value or "").replace("{", "").replace("}", "").strip()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value)


def author_signature(value: str) -> str:
    value = (value or "").replace("{", "").replace("}", "").strip()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    people = [p.strip() for p in value.split(" and ") if p.strip()]
    surnames: list[str] = []

    for person in people:
        if "," in person:
            left = person.split(",", 1)[0].strip()
            left = re.sub(r"[^a-z0-9 ]+", " ", left)
            toks = [t for t in left.split() if t]
            for tok in reversed(toks):
                if re.search(r"[a-z]", tok):
                    surnames.append(tok)
                    break
            continue

        cleaned = re.sub(r"[^a-z0-9 ]+", " ", person)
        toks = [t for t in cleaned.split() if t]
        for tok in reversed(toks):
            if re.search(r"[a-z]", tok):
                surnames.append(tok)
                break

    return " ".join(surnames)


def matches_any_glob(path: Path, globs: Iterable[str]) -> bool:
    s = str(path)
    for g in globs:
        if path.match(g):
            return True
        if g.startswith("**/") and s.endswith(g[3:]):
            return True
    return False


def discover_bib_files(cfg: OpsConfig) -> list[Path]:
    files: list[Path] = []
    for root in cfg.roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for p in root_path.rglob("*.bib"):
            if matches_any_glob(p, cfg.exclude_globs):
                continue
            files.append(p)
    return sorted(set(files))


def parse_bib(path: Path):
    data = path.read_text(encoding="utf-8")

    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    try:
        return bibtexparser.loads(data, parser=parser)
    except Exception:
        # Fallback for legacy files that break unicode customization.
        parser_fallback = BibTexParser(common_strings=True)
        parser_fallback.ignore_nonstandard_types = False
        return bibtexparser.loads(data, parser=parser_fallback)


def file_is_dblp_generated(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as f:
            head = "".join([next(f, "") for _ in range(8)]).lower()
    except OSError:
        return False
    return "generated from dblp xml dump" in head


def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            files_scanned INTEGER DEFAULT 0,
            entries_scanned INTEGER DEFAULT 0,
            issues_found INTEGER DEFAULT 0,
            payload_json TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_file_stats (
            run_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            parse_ok INTEGER NOT NULL,
            entry_count INTEGER NOT NULL,
            error_message TEXT,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            PRIMARY KEY (run_id, file_path)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_entry_stats (
            run_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            entry_key TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            year TEXT,
            title_norm TEXT,
            has_url INTEGER NOT NULL,
            has_pdf INTEGER NOT NULL,
            has_file INTEGER NOT NULL,
            PRIMARY KEY (run_id, file_path, entry_key)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_issues (
            run_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            entry_key TEXT,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def _pid_looks_like_bibops(pid: int) -> bool:
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if not proc_cmdline.exists():
        return False
    try:
        raw = proc_cmdline.read_bytes()
    except Exception:
        return True
    if not raw:
        return False
    text = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
    return "bibops.py" in text or "bibops" in text


@contextlib.contextmanager
def run_lock() -> Iterable[None]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    try:
        if LOCK_PATH.exists():
            # Clear stale lock left by an interrupted process.
            try:
                pid_txt = LOCK_PATH.read_text(encoding="utf-8").strip()
                pid = int(pid_txt)
            except Exception:
                pid = -1

            if pid > 0:
                try:
                    os.kill(pid, 0)
                    if _pid_looks_like_bibops(pid):
                        raise RuntimeError(f"Another bibops process is running (pid={pid})")
                    LOCK_PATH.unlink(missing_ok=True)
                except ProcessLookupError:
                    LOCK_PATH.unlink(missing_ok=True)
            else:
                LOCK_PATH.unlink(missing_ok=True)

        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()


class RunRecorder:
    def __init__(self, db_path: Path, command: str):
        self.db_path = db_path
        self.command = command
        self.run_id = uuid.uuid4().hex
        self.started_at = now_iso()

    def start(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ops_runs (run_id, started_at, command, status) VALUES (?, ?, ?, ?)",
            (self.run_id, self.started_at, self.command, "running"),
        )
        conn.commit()
        conn.close()

    def finish(
        self,
        status: str,
        files_scanned: int,
        entries_scanned: int,
        issues_found: int,
        payload: dict[str, object],
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE ops_runs
            SET finished_at = ?, status = ?, files_scanned = ?, entries_scanned = ?, issues_found = ?, payload_json = ?
            WHERE run_id = ?
            """,
            (
                now_iso(),
                status,
                files_scanned,
                entries_scanned,
                issues_found,
                json.dumps(payload, sort_keys=True),
                self.run_id,
            ),
        )
        conn.commit()
        conn.close()


def write_file_stats(db_path: Path, run_id: str, rows: list[FileResult]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR REPLACE INTO ops_file_stats
        (run_id, file_path, parse_ok, entry_count, error_message, mtime, size, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                r.file_path,
                1 if r.parse_ok else 0,
                r.entry_count,
                r.error_message,
                r.mtime,
                r.size,
                r.sha256,
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


def write_entry_stats(db_path: Path, run_id: str, rows: list[EntryResult]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR REPLACE INTO ops_entry_stats
        (run_id, file_path, entry_key, entry_type, year, title_norm, has_url, has_pdf, has_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                r.file_path,
                r.entry_key,
                r.entry_type,
                r.year,
                r.title_norm,
                1 if r.has_url else 0,
                1 if r.has_pdf else 0,
                1 if r.has_file else 0,
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


def write_issues(db_path: Path, run_id: str, rows: list[Issue]) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO ops_issues
        (run_id, file_path, entry_key, issue_type, severity, message, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                r.file_path,
                r.entry_key,
                r.issue_type,
                r.severity,
                r.message,
                json.dumps(r.details, sort_keys=True),
                now_iso(),
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()


def run_scan(cfg: OpsConfig) -> tuple[list[FileResult], list[EntryResult], list[Issue]]:
    file_rows: list[FileResult] = []
    entry_rows: list[EntryResult] = []
    issues: list[Issue] = []

    for bib_file in discover_bib_files(cfg):
        st = bib_file.stat()
        digest = file_sha256(bib_file)
        try:
            db = parse_bib(bib_file)
            entries = db.entries
            file_rows.append(
                FileResult(
                    file_path=str(bib_file),
                    parse_ok=True,
                    entry_count=len(entries),
                    error_message=None,
                    mtime=st.st_mtime,
                    size=st.st_size,
                    sha256=digest,
                )
            )

            for e in entries:
                entry_rows.append(
                    EntryResult(
                        file_path=str(bib_file),
                        entry_key=str(e.get("ID", "")),
                        entry_type=str(e.get("ENTRYTYPE", "")),
                        year=str(e.get("year", "")),
                        title_norm=norm_title(str(e.get("title", ""))),
                        doi_raw=str(e.get("doi", "")).strip().lower(),
                        url_fp=url_fingerprint(str(e.get("url", ""))),
                        has_author=bool(e.get("author")),
                        has_title=bool(e.get("title")),
                        has_booktitle=bool(e.get("booktitle")),
                        author_raw=str(e.get("author", "")),
                        has_url=bool(e.get("url")),
                        has_pdf=bool(e.get("pdf")),
                        has_file=bool(e.get("file")),
                    )
                )
        except Exception as ex:
            file_rows.append(
                FileResult(
                    file_path=str(bib_file),
                    parse_ok=False,
                    entry_count=0,
                    error_message=str(ex),
                    mtime=st.st_mtime,
                    size=st.st_size,
                    sha256=digest,
                )
            )
            issues.append(
                Issue(
                    file_path=str(bib_file),
                    entry_key=None,
                    issue_type="parse_error",
                    severity="error",
                    message="Failed to parse BibTeX file",
                    details={"error": str(ex)},
                )
            )

    return file_rows, entry_rows, issues


def key_format_issues(key: str, year: str) -> list[str]:
    out: list[str] = []
    if not key:
        return ["missing key"]
    if not re.match(r"^[a-z0-9]+$", key):
        out.append("key must be lowercase alphanumeric only")
    m = re.search(r"\d{4}", key)
    if not m:
        out.append("key must include year")
    else:
        if m.group(0) != year and year:
            out.append("key year does not match entry year")
        if m.end() == len(key):
            out.append("key missing keyword after year")
    return out


def run_lint(cfg: OpsConfig, file_rows: list[FileResult], entry_rows: list[EntryResult]) -> list[Issue]:
    issues: list[Issue] = []
    issue_counts: dict[str, int] = {}
    suppressed_counts: dict[str, int] = {}
    generic_duplicate_titles = {
        "editorial",
        "announcement",
        "erratum",
        "publisher s note",
        "corrigendum",
        "addendum",
    }

    def add_issue(issue: Issue) -> None:
        c = issue_counts.get(issue.issue_type, 0)
        if c < cfg.issue_limit_per_type:
            issues.append(issue)
            issue_counts[issue.issue_type] = c + 1
        else:
            suppressed_counts[issue.issue_type] = suppressed_counts.get(issue.issue_type, 0) + 1

    by_file: dict[str, list[EntryResult]] = {}
    for r in entry_rows:
        by_file.setdefault(r.file_path, []).append(r)

    by_key_global: dict[str, list[EntryResult]] = {}
    for r in entry_rows:
        by_key_global.setdefault(r.entry_key, []).append(r)

    generated_file_cache: dict[str, bool] = {}

    def is_generated_file(file_path: str) -> bool:
        cached = generated_file_cache.get(file_path)
        if cached is not None:
            return cached
        generated = file_is_dblp_generated(Path(file_path))
        generated_file_cache[file_path] = generated
        return generated

    for file_path, rows in by_file.items():
        local_key_map: dict[str, list[EntryResult]] = {}
        local_title_author_map: dict[tuple[str, str], list[EntryResult]] = {}
        local_title_year_map: dict[tuple[str, str], list[EntryResult]] = {}

        for r in rows:
            local_key_map.setdefault(r.entry_key, []).append(r)
            if r.title_norm:
                sig = author_signature(r.author_raw)
                if sig:
                    local_title_author_map.setdefault((r.title_norm, sig), []).append(r)
                elif r.year:
                    local_title_year_map.setdefault((r.title_norm, r.year), []).append(r)

        for k, ks in local_key_map.items():
            if k and len(ks) > 1:
                add_issue(
                    Issue(
                        file_path=file_path,
                        entry_key=k,
                        issue_type="duplicate_key_in_file",
                        severity="error",
                        message=f"Duplicate key in file: {k}",
                        details={"count": str(len(ks))},
                    )
                )

        for (t, sig), ts in local_title_author_map.items():
            if len(ts) > 1:
                if t in generic_duplicate_titles:
                    continue
                ids = [(r.doi_raw or r.url_fp) for r in ts]
                if all(ids) and len(set(ids)) == len(ids):
                    continue
                add_issue(
                    Issue(
                        file_path=file_path,
                        entry_key=ts[0].entry_key,
                        issue_type="duplicate_title_in_file",
                        severity="warning",
                        message="Duplicate normalized title in file",
                        details={
                            "title": t,
                            "count": str(len(ts)),
                            "match_basis": "title+author_signature",
                            "author_signature": sig,
                        },
                    )
                )

        for (t, y), ts in local_title_year_map.items():
            if len(ts) > 1:
                if t in generic_duplicate_titles:
                    continue
                ids = [(r.doi_raw or r.url_fp) for r in ts]
                if all(ids) and len(set(ids)) == len(ids):
                    continue
                add_issue(
                    Issue(
                        file_path=file_path,
                        entry_key=ts[0].entry_key,
                        issue_type="duplicate_title_in_file",
                        severity="warning",
                        message="Duplicate normalized title in file",
                        details={
                            "title": t,
                            "count": str(len(ts)),
                            "match_basis": "title+year(no_author)",
                            "year": y,
                        },
                    )
                )

    for k, rows in by_key_global.items():
        file_set = {r.file_path for r in rows}
        if not k or len(file_set) <= 1:
            continue

        # Only flag global key duplicates when they collide across distinct
        # entry signatures; mirrored subsets intentionally re-use keys.
        signatures = {
            (r.year, r.title_norm, author_signature(r.author_raw))
            for r in rows
        }
        if len(signatures) > 1:
            add_issue(
                Issue(
                    file_path="*",
                    entry_key=k,
                    issue_type="duplicate_key_global",
                    severity="warning",
                    message="Key maps to multiple distinct entries across files",
                    details={
                        "files": ", ".join(sorted(file_set)),
                        "distinct_signatures": str(len(signatures)),
                    },
                )
            )

    for r in entry_rows:
        key = r.entry_key
        entry_type = r.entry_type.lower()
        year = r.year

        if not is_generated_file(r.file_path):
            for msg in key_format_issues(key, year):
                add_issue(
                    Issue(
                        file_path=r.file_path,
                        entry_key=key,
                        issue_type="key_format",
                        severity="warning",
                        message=msg,
                        details={"key": key, "year": year},
                    )
                )

        if entry_type == "inproceedings":
            missing: list[str] = []
            if not r.has_author:
                missing.append("author")
            if not r.has_title:
                missing.append("title")
            if not r.has_booktitle:
                missing.append("booktitle")
            if not year:
                missing.append("year")
            if missing:
                add_issue(
                    Issue(
                        file_path=r.file_path,
                        entry_key=key,
                        issue_type="missing_required_fields",
                        severity="error",
                        message="inproceedings entry missing mandatory fields",
                        details={"missing": ", ".join(missing)},
                    )
                )

        author = r.author_raw.lower()
        if "and others" in author or "others}" in author:
            add_issue(
                Issue(
                    file_path=r.file_path,
                    entry_key=key,
                    issue_type="placeholder_authors",
                    severity="warning",
                    message="Author field includes placeholder 'others'",
                    details={},
                )
            )

    for issue_type, suppressed in sorted(suppressed_counts.items()):
        add_issue(
            Issue(
                file_path="*",
                entry_key=None,
                issue_type="issue_limit_reached",
                severity="info",
                message=f"Suppressed {suppressed} additional `{issue_type}` issues (limit={cfg.issue_limit_per_type})",
                details={"suppressed_type": issue_type, "suppressed_count": str(suppressed)},
            )
        )

    return issues


def oral_identity(path: Path) -> tuple[str, str] | None:
    try:
        rel = path.relative_to(ORALS_ROOT)
    except ValueError:
        return None

    if len(rel.parts) != 2:
        return None
    venue = rel.parts[0]
    year = rel.stem
    if not re.match(r"^[a-z0-9]+$", venue):
        return None
    if not re.match(r"^(19|20)\d{2}$", year):
        return None
    return venue, year


def extract_openreview_id(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"[?&]id=([^&#]+)", url)
    if not m:
        return ""
    return m.group(1).strip()


def url_fingerprint(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = u.rstrip("/")
    return u


def run_verify_orals(cfg: OpsConfig) -> tuple[int, int, list[Issue]]:
    issues: list[Issue] = []
    issue_counts: dict[str, int] = {}
    suppressed_counts: dict[str, int] = {}
    files_scanned = 0
    entries_scanned = 0
    canonical_cache: dict[
        Path,
        tuple[
            dict[str, dict[str, object]],
            dict[str, list[dict[str, object]]],
            dict[str, list[dict[str, object]]],
            dict[str, list[dict[str, object]]],
            str | None,
        ],
    ] = {}
    matched_by_title = 0
    matched_by_openreview = 0
    matched_by_link = 0

    def add_issue(issue: Issue) -> None:
        c = issue_counts.get(issue.issue_type, 0)
        if c < cfg.issue_limit_per_type:
            issues.append(issue)
            issue_counts[issue.issue_type] = c + 1
        else:
            suppressed_counts[issue.issue_type] = suppressed_counts.get(issue.issue_type, 0) + 1

    if not ORALS_ROOT.exists():
        add_issue(
            Issue(
                file_path=str(ORALS_ROOT),
                entry_key=None,
                issue_type="orals_root_missing",
                severity="warning",
                message="Derived oral collections root not found",
                details={},
            )
        )
        return files_scanned, entries_scanned, issues

    oral_files = sorted(ORALS_ROOT.rglob("*.bib"))
    if not oral_files:
        add_issue(
            Issue(
                file_path=str(ORALS_ROOT),
                entry_key=None,
                issue_type="orals_files_missing",
                severity="warning",
                message="No oral BibTeX files found under collections/orals",
                details={},
            )
        )
        return files_scanned, entries_scanned, issues

    for oral_file in oral_files:
        files_scanned += 1
        ident = oral_identity(oral_file)
        if ident is None:
            add_issue(
                Issue(
                    file_path=str(oral_file),
                    entry_key=None,
                    issue_type="oral_path_invalid",
                    severity="warning",
                    message="Oral file path must match collections/orals/<venue>/<year>.bib",
                    details={},
                )
            )
            continue
        venue, year = ident

        try:
            oral_db = parse_bib(oral_file)
        except Exception as ex:
            add_issue(
                Issue(
                    file_path=str(oral_file),
                    entry_key=None,
                    issue_type="parse_error",
                    severity="error",
                    message="Failed to parse oral BibTeX file",
                    details={"error": str(ex)},
                )
            )
            continue

        oral_entries = oral_db.entries
        entries_scanned += len(oral_entries)

        canonical_path = CANONICAL_CONFERENCES_ROOT / venue / f"{year}.bib"
        canonical_entries_by_key: dict[str, dict[str, object]] | None = None
        canonical_entries_by_title: dict[str, list[dict[str, object]]] | None = None
        canonical_entries_by_openreview: dict[str, list[dict[str, object]]] | None = None
        canonical_entries_by_link: dict[str, list[dict[str, object]]] | None = None

        if canonical_path.exists():
            if canonical_path not in canonical_cache:
                try:
                    canonical_db = parse_bib(canonical_path)
                    entries_by_key: dict[str, dict[str, object]] = {}
                    entries_by_title: dict[str, list[dict[str, object]]] = {}
                    entries_by_openreview: dict[str, list[dict[str, object]]] = {}
                    entries_by_link: dict[str, list[dict[str, object]]] = {}
                    for e in canonical_db.entries:
                        canonical_key = str(e.get("ID", ""))
                        canonical_title = norm_title(str(e.get("title", "")))
                        canonical_or_id = extract_openreview_id(str(e.get("url", "")))
                        if not canonical_or_id:
                            canonical_or_id = extract_openreview_id(str(e.get("pdf", "")))
                        for field in ("url", "pdf"):
                            fp = url_fingerprint(str(e.get(field, "")))
                            if fp:
                                entries_by_link.setdefault(fp, []).append(e)
                        if canonical_key:
                            entries_by_key[canonical_key] = e
                        if canonical_title:
                            entries_by_title.setdefault(canonical_title, []).append(e)
                        if canonical_or_id:
                            entries_by_openreview.setdefault(canonical_or_id, []).append(e)
                    canonical_cache[canonical_path] = (
                        entries_by_key,
                        entries_by_title,
                        entries_by_openreview,
                        entries_by_link,
                        None,
                    )
                except Exception as ex:
                    canonical_cache[canonical_path] = ({}, {}, {}, {}, str(ex))
            cached_entries, cached_titles, cached_openreview, cached_links, cached_error = canonical_cache[canonical_path]
            if cached_error:
                add_issue(
                    Issue(
                        file_path=str(oral_file),
                        entry_key=None,
                        issue_type="canonical_parse_error",
                        severity="error",
                        message="Failed to parse canonical conference BibTeX file",
                        details={"canonical_file": str(canonical_path), "error": cached_error},
                    )
                )
            else:
                canonical_entries_by_key = cached_entries
                canonical_entries_by_title = cached_titles
                canonical_entries_by_openreview = cached_openreview
                canonical_entries_by_link = cached_links
        else:
            add_issue(
                Issue(
                    file_path=str(oral_file),
                    entry_key=None,
                    issue_type="canonical_file_missing",
                    severity="warning",
                    message="No canonical conference file for this oral subset year",
                    details={"canonical_file": str(canonical_path)},
                )
            )

        for entry in oral_entries:
            key = str(entry.get("ID", ""))
            if not key:
                add_issue(
                    Issue(
                        file_path=str(oral_file),
                        entry_key=None,
                        issue_type="oral_missing_key",
                        severity="error",
                        message="Oral entry is missing an ID key",
                        details={},
                    )
                )
                continue

            for field in ("url", "pdf"):
                val = str(entry.get(field, "")).strip()
                if not val:
                    add_issue(
                        Issue(
                            file_path=str(oral_file),
                            entry_key=key,
                            issue_type="oral_missing_link_field",
                            severity="error",
                            message=f"Oral entry missing required `{field}` field",
                            details={"field": field},
                        )
                    )
                    continue
                if not HTTP_URL_RE.match(val):
                    add_issue(
                        Issue(
                            file_path=str(oral_file),
                            entry_key=key,
                            issue_type="oral_link_not_http",
                            severity="warning",
                            message=f"Oral `{field}` field is not an HTTP(S) URL",
                            details={"field": field, "value": val},
                        )
                    )

            if canonical_entries_by_key is None:
                continue

            oral_title = norm_title(str(entry.get("title", "")))
            oral_or_id = extract_openreview_id(str(entry.get("url", "")))
            if not oral_or_id:
                oral_or_id = extract_openreview_id(str(entry.get("pdf", "")))
            oral_link_candidates: list[str] = []
            for field in ("url", "pdf"):
                fp = url_fingerprint(str(entry.get(field, "")))
                if fp:
                    oral_link_candidates.append(fp)

            match_mode = "key"
            canonical_entry = canonical_entries_by_key.get(key)
            if canonical_entry is None:
                title_candidates: list[dict[str, object]] = []
                if oral_title and canonical_entries_by_title is not None:
                    title_candidates = canonical_entries_by_title.get(oral_title, [])

                if len(title_candidates) == 1:
                    canonical_entry = title_candidates[0]
                    match_mode = "title"
                elif len(title_candidates) > 1:
                    add_issue(
                        Issue(
                            file_path=str(oral_file),
                            entry_key=key,
                            issue_type="oral_title_match_ambiguous",
                            severity="error",
                            message="Oral title maps to multiple canonical entries",
                            details={
                                "canonical_file": str(canonical_path),
                                "candidate_count": str(len(title_candidates)),
                            },
                        )
                    )
                    continue
                else:
                    openreview_candidates: list[dict[str, object]] = []
                    if oral_or_id and canonical_entries_by_openreview is not None:
                        openreview_candidates = canonical_entries_by_openreview.get(oral_or_id, [])

                    if len(openreview_candidates) == 1:
                        canonical_entry = openreview_candidates[0]
                        match_mode = "openreview"
                    elif len(openreview_candidates) > 1:
                        add_issue(
                            Issue(
                                file_path=str(oral_file),
                                entry_key=key,
                                issue_type="oral_openreview_match_ambiguous",
                                severity="error",
                                message="Oral OpenReview ID maps to multiple canonical entries",
                                details={
                                    "canonical_file": str(canonical_path),
                                    "candidate_count": str(len(openreview_candidates)),
                                },
                            )
                        )
                        continue
                    else:
                        link_candidates: list[dict[str, object]] = []
                        if canonical_entries_by_link is not None:
                            for fp in oral_link_candidates:
                                link_candidates.extend(canonical_entries_by_link.get(fp, []))
                        # Deduplicate candidate entries by key.
                        uniq: dict[str, dict[str, object]] = {}
                        for cand in link_candidates:
                            uniq[str(cand.get("ID", ""))] = cand
                        link_candidates = list(uniq.values())

                        if len(link_candidates) == 1:
                            canonical_entry = link_candidates[0]
                            match_mode = "link"
                        elif len(link_candidates) > 1:
                            add_issue(
                                Issue(
                                    file_path=str(oral_file),
                                    entry_key=key,
                                    issue_type="oral_link_match_ambiguous",
                                    severity="error",
                                    message="Oral URL/PDF maps to multiple canonical entries",
                                    details={
                                        "canonical_file": str(canonical_path),
                                        "candidate_count": str(len(link_candidates)),
                                    },
                                )
                            )
                            continue
                        else:
                            add_issue(
                                Issue(
                                    file_path=str(oral_file),
                                    entry_key=key,
                                    issue_type="oral_key_not_in_canonical",
                                    severity="error",
                                    message="Oral entry not found in canonical conference file",
                                    details={"canonical_file": str(canonical_path)},
                                )
                            )
                            continue

            canonical_title = norm_title(str(canonical_entry.get("title", "")))
            if oral_title and canonical_title and oral_title != canonical_title:
                add_issue(
                    Issue(
                        file_path=str(oral_file),
                        entry_key=key,
                        issue_type="oral_title_mismatch",
                        severity="info",
                        message="Oral title differs from canonical conference entry",
                        details={"canonical_file": str(canonical_path)},
                    )
                )

            oral_year = str(entry.get("year", "")).strip()
            canonical_year = str(canonical_entry.get("year", "")).strip()
            if oral_year and canonical_year and oral_year != canonical_year:
                add_issue(
                    Issue(
                        file_path=str(oral_file),
                        entry_key=key,
                        issue_type="oral_year_mismatch",
                        severity="error",
                        message="Oral year differs from canonical conference entry",
                        details={"canonical_file": str(canonical_path)},
                    )
                )

            oral_author = author_signature(str(entry.get("author", "")))
            canonical_author = author_signature(str(canonical_entry.get("author", "")))
            if match_mode == "key" and oral_author and canonical_author and oral_author != canonical_author:
                add_issue(
                    Issue(
                        file_path=str(oral_file),
                        entry_key=key,
                        issue_type="oral_author_mismatch",
                        severity="info",
                        message="Oral author field differs from canonical conference entry",
                        details={"canonical_file": str(canonical_path)},
                    )
                )
            elif match_mode == "title":
                matched_by_title += 1
            elif match_mode == "openreview":
                matched_by_openreview += 1
            elif match_mode == "link":
                matched_by_link += 1

    if matched_by_title:
        issues.append(
            Issue(
                file_path="*",
                entry_key=None,
                issue_type="oral_key_mismatch_title_match",
                severity="info",
                message=f"{matched_by_title} oral entries matched canonical by title despite key differences",
                details={"count": str(matched_by_title)},
            )
        )

    if matched_by_openreview:
        issues.append(
            Issue(
                file_path="*",
                entry_key=None,
                issue_type="oral_key_mismatch_openreview_match",
                severity="info",
                message=f"{matched_by_openreview} oral entries matched canonical by OpenReview ID despite key differences",
                details={"count": str(matched_by_openreview)},
            )
        )

    if matched_by_link:
        issues.append(
            Issue(
                file_path="*",
                entry_key=None,
                issue_type="oral_key_mismatch_link_match",
                severity="info",
                message=f"{matched_by_link} oral entries matched canonical by URL/PDF despite key differences",
                details={"count": str(matched_by_link)},
            )
        )

    for issue_type, suppressed in sorted(suppressed_counts.items()):
        issues.append(
            Issue(
                file_path="*",
                entry_key=None,
                issue_type="issue_limit_reached",
                severity="info",
                message=f"Suppressed {suppressed} additional `{issue_type}` issues (limit={cfg.issue_limit_per_type})",
                details={"suppressed_type": issue_type, "suppressed_count": str(suppressed)},
            )
        )

    return files_scanned, entries_scanned, issues


def print_summary(run_id: str, file_rows: list[FileResult], entry_rows: list[EntryResult], issues: list[Issue]) -> None:
    parse_errors = sum(1 for r in file_rows if not r.parse_ok)
    by_sev: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for i in issues:
        by_sev[i.severity] = by_sev.get(i.severity, 0) + 1
        by_type[i.issue_type] = by_type.get(i.issue_type, 0) + 1

    print(f"run_id: {run_id}")
    print(f"files_scanned: {len(file_rows)}")
    print(f"entries_scanned: {len(entry_rows)}")
    print(f"parse_errors: {parse_errors}")
    print(f"issues_found: {len(issues)}")
    if by_sev:
        print("issues_by_severity:")
        for k in sorted(by_sev):
            print(f"  {k}: {by_sev[k]}")
    if by_type:
        print("issues_by_type:")
        for k in sorted(by_type):
            print(f"  {k}: {by_type[k]}")


def collect_bibmeta_issues() -> list[Issue]:
    _manifest, diagnostics, _resolved = validate_repo_bibmeta(Path("."))
    issues: list[Issue] = []
    for diag in diagnostics:
        issues.append(
            Issue(
                file_path=diag.file_path,
                entry_key=None,
                issue_type=f"bibmeta_{diag.code}",
                severity=diag.severity,
                message=diag.message,
                details=diag.details,
            )
        )
    return issues


def command_doctor(cfg: OpsConfig) -> int:
    problems: list[str] = []
    warnings: list[str] = []

    if shutil.which("guix") is None:
        problems.append("guix not found in PATH")

    if not Path(cfg.db_path).exists():
        print(f"INFO: database not found at {cfg.db_path}; will be created on first run")

    if not Path("hooks/pre-commit").exists() or not Path("hooks/commit-msg").exists():
        problems.append("versioned hooks missing under hooks/")

    if not Path("scripts/install-hooks.py").exists():
        problems.append("scripts/install-hooks.py missing")
    else:
        # Check whether installed hooks are managed wrappers that execute
        # versioned hooks/, so hook updates are automatically picked up.
        for hook_name in ("pre-commit", "commit-msg"):
            installed = Path(".git/hooks") / hook_name
            if not installed.exists():
                warnings.append(f"{installed} missing; run `python3 scripts/install-hooks.py`")
                continue
            try:
                content = installed.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                warnings.append(f"unable to read {installed}; run `python3 scripts/install-hooks.py`")
                continue
            if "Managed by scripts/install-hooks.py" not in content:
                warnings.append(
                    f"{installed} is not managed by install-hooks and may drift from versioned hooks"
                )

    discovered = discover_bib_files(cfg)
    if not discovered:
        problems.append("no .bib files discovered from configured roots")

    bibmeta_issues = collect_bibmeta_issues()
    bibmeta_errors = [issue for issue in bibmeta_issues if issue.severity == "error"]
    if bibmeta_errors:
        problems.append(
            f"bibmeta validation failed with {len(bibmeta_errors)} error(s); see `python3 scripts/bibops.py lint --fail-on-error`"
        )

    if problems:
        print("doctor: FAILED")
        for p in problems:
            print(f"- {p}")
        if bibmeta_errors:
            print("- bibmeta_errors:")
            for issue in bibmeta_errors[:10]:
                print(f"  - {issue.file_path}: {issue.message}")
            if len(bibmeta_errors) > 10:
                print(f"  - ... and {len(bibmeta_errors) - 10} more")
        return 2

    print("doctor: OK")
    print(f"- discovered_bib_files: {len(discovered)}")
    print(f"- db_path: {cfg.db_path}")
    if warnings:
        print("- warnings:")
        for w in warnings:
            print(f"  - {w}")
    return 0


def command_scan(cfg: OpsConfig, recorder: RunRecorder, as_json: bool) -> int:
    file_rows, entry_rows, issues = run_scan(cfg)
    write_file_stats(Path(cfg.db_path), recorder.run_id, file_rows)
    write_entry_stats(Path(cfg.db_path), recorder.run_id, entry_rows)
    write_issues(Path(cfg.db_path), recorder.run_id, issues)

    payload = {
        "parse_errors": sum(1 for r in file_rows if not r.parse_ok),
    }
    recorder.finish(
        status="ok",
        files_scanned=len(file_rows),
        entries_scanned=len(entry_rows),
        issues_found=len(issues),
        payload=payload,
    )

    if as_json:
        print(json.dumps({"run_id": recorder.run_id, **payload}, indent=2, sort_keys=True))
    else:
        print_summary(recorder.run_id, file_rows, entry_rows, issues)
    return 0


def command_lint(cfg: OpsConfig, recorder: RunRecorder, as_json: bool, fail_on_error: bool) -> int:
    file_rows, entry_rows, scan_issues = run_scan(cfg)
    lint_issues = run_lint(cfg, file_rows, entry_rows)
    bibmeta_issues = collect_bibmeta_issues()
    issues = scan_issues + lint_issues + bibmeta_issues

    write_file_stats(Path(cfg.db_path), recorder.run_id, file_rows)
    write_entry_stats(Path(cfg.db_path), recorder.run_id, entry_rows)
    write_issues(Path(cfg.db_path), recorder.run_id, issues)

    error_count = sum(1 for i in issues if i.severity == "error")
    payload = {
        "parse_errors": sum(1 for r in file_rows if not r.parse_ok),
        "errors": error_count,
        "warnings": sum(1 for i in issues if i.severity == "warning"),
    }
    recorder.finish(
        status="ok" if error_count == 0 else "issues",
        files_scanned=len(file_rows),
        entries_scanned=len(entry_rows),
        issues_found=len(issues),
        payload=payload,
    )

    if as_json:
        print(
            json.dumps(
                {
                    "run_id": recorder.run_id,
                    "summary": payload,
                    "issues": [dataclasses.asdict(i) for i in issues],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_summary(recorder.run_id, file_rows, entry_rows, issues)

    if fail_on_error and error_count > 0:
        return 3
    return 0


def command_report(cfg: OpsConfig, run_id: str | None, as_json: bool) -> int:
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if run_id:
        cur.execute("SELECT * FROM ops_runs WHERE run_id = ?", (run_id,))
    else:
        cur.execute("SELECT * FROM ops_runs ORDER BY started_at DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        print("No ops runs found")
        conn.close()
        return 1

    rid = row["run_id"]
    cur.execute("SELECT severity, COUNT(*) AS c FROM ops_issues WHERE run_id = ? GROUP BY severity", (rid,))
    sev = {r["severity"]: r["c"] for r in cur.fetchall()}
    cur.execute("SELECT issue_type, COUNT(*) AS c FROM ops_issues WHERE run_id = ? GROUP BY issue_type", (rid,))
    typ = {r["issue_type"]: r["c"] for r in cur.fetchall()}

    payload = {
        "run": dict(row),
        "issues_by_severity": sev,
        "issues_by_type": typ,
    }

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(f"run_id: {rid}")
        print(f"command: {row['command']}")
        print(f"status: {row['status']}")
        print(f"started_at: {row['started_at']}")
        print(f"finished_at: {row['finished_at']}")
        print(f"files_scanned: {row['files_scanned']}")
        print(f"entries_scanned: {row['entries_scanned']}")
        print(f"issues_found: {row['issues_found']}")
        if sev:
            print("issues_by_severity:")
            for k in sorted(sev):
                print(f"  {k}: {sev[k]}")
        if typ:
            print("issues_by_type:")
            for k in sorted(typ):
                print(f"  {k}: {typ[k]}")

    conn.close()
    return 0


def command_install_hooks() -> int:
    proc = subprocess.run([sys.executable, "scripts/install-hooks.py"], check=False)
    return proc.returncode


def command_export_tracking(cfg: OpsConfig) -> int:
    proc = subprocess.run(
        [sys.executable, "scripts/export-tracking.py", cfg.tracking_export],
        check=False,
    )
    return proc.returncode


def command_enrich_pipeline(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "scripts/enrich-pipeline.py", "--config", args.enrichment_config, args.mode, *args.targets]
    if args.entry_key:
        for key in args.entry_key:
            cmd.extend(["--entry-key", key])
    if args.max_entries:
        cmd.extend(["--max-entries", str(args.max_entries)])
    if args.overwrite:
        cmd.append("--overwrite")
    if args.write:
        cmd.append("--write")
    if args.resume:
        cmd.append("--resume")
    if args.checkpoint_path:
        cmd.extend(["--checkpoint-path", args.checkpoint_path])
    if args.fail_on_unresolved:
        cmd.append("--fail-on-unresolved")
    if args.verbose_entry_log:
        cmd.append("--verbose-entry-log")
    if args.progress_log:
        cmd.extend(["--progress-log", args.progress_log])
    if args.json:
        cmd.append("--json")
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def command_intake_pipeline(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "scripts/intake-pipeline.py", "--config", args.intake_config, args.mode, *args.targets]
    if args.mode in {"plan", "run"} and args.max_records:
        cmd.extend(["--max-records", str(args.max_records)])
    if args.mode == "run" and args.write:
        cmd.append("--write")
    if args.mode in {"plan", "run"} and args.fail_on_gap:
        cmd.append("--fail-on-gap")
    out_path = getattr(args, "out", None)
    if out_path:
        cmd.extend(["--out", str(out_path)])
    if args.json:
        cmd.append("--json")
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def command_pdf_sync(args: argparse.Namespace) -> int:
    try:
        host_overrides = parse_host_interval_overrides(args.host_interval or [])
    except ValueError as ex:
        print(f"Invalid --host-interval value: {ex}")
        return 2

    options = PdfSyncOptions(
        targets=args.targets,
        base_dir=Path(args.base_dir),
        download=not args.no_download,
        fix_existing=not args.no_fix,
        dry_run=args.dry_run,
        verify_existing=not args.no_verify_existing,
        smart_url_derivation=not args.no_smart_url_derivation,
        max_entries=max(0, args.max_entries),
        max_attempts=max(1, args.max_attempts),
        timeout_connect_seconds=max(1.0, args.timeout_connect),
        timeout_read_seconds=max(1.0, args.timeout_read),
        max_attempt_wall_seconds=max(0.0, args.max_attempt_wall_seconds),
        max_pdf_size_mb=max(1, args.max_pdf_size_mb),
        backoff_base_seconds=max(0.0, args.backoff_base_seconds),
        backoff_max_seconds=max(0.0, args.backoff_max_seconds),
        backoff_jitter_seconds=max(0.0, args.backoff_jitter_seconds),
        host_default_min_interval_seconds=max(0.0, args.host_min_interval_seconds),
        host_min_interval_seconds_by_host=host_overrides,
        checkpoint_path=Path(args.checkpoint_path) if args.checkpoint_path else None,
        resume=not args.no_resume,
        retry_failures=args.retry_failures,
        progress_log=Path(args.progress_log) if args.progress_log else None,
        console_progress=args.console_progress,
        checkpoint_flush_seconds=max(0.0, args.checkpoint_flush_seconds),
        max_consecutive_failures=max(1, args.max_consecutive_failures),
        user_agent=args.user_agent,
        policy_path=Path(args.pdf_sync_policy) if args.pdf_sync_policy else None,
    )

    try:
        result = run_pdf_sync(options)
    except Exception as ex:
        print(f"pdf-sync failed: {ex}")
        if args.json:
            print(json.dumps({"status": "failed", "error": str(ex)}, indent=2, sort_keys=True))
        return 1

    summary = result.summary
    failed = int(summary.get("failed", 0))
    unresolved_targets = int(summary.get("unresolved_targets", 0))
    aborted = int(summary.get("aborted", 0))

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "failures": [dataclasses.asdict(f) for f in result.failures],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("pdf-sync summary:")
        for key in sorted(summary):
            print(f"  {key}: {summary[key]}")

        if result.failures:
            print("failed_entries:")
            for failure in result.failures[:25]:
                print(f"  {failure.bib_file} :: {failure.key} :: {failure.message}")
            if len(result.failures) > 25:
                print(f"  ... and {len(result.failures) - 25} more")

    if args.fail_on_error and (failed > 0 or unresolved_targets > 0 or aborted > 0):
        return 4
    return 0


def command_key_normalize(cfg: OpsConfig, args: argparse.Namespace) -> int:
    global_paths: list[Path] = []
    if args.global_scope == "config":
        global_paths = discover_bib_files(cfg)

    options = KeyNormalizeOptions(
        targets=args.targets,
        write=args.write,
        canonicalize_all=args.canonicalize_all,
        max_entries=max(0, args.max_entries),
        global_scope=args.global_scope,
        global_paths=global_paths,
        fail_on_issues=args.fail_on_issues,
        detail_limit=max(1, args.detail_limit),
        backup=not args.no_backup,
        rollback_dir=Path(args.rollback_dir) if args.rollback_dir else None,
    )

    try:
        result = run_key_normalize(options)
    except Exception as ex:
        print(f"key-normalize failed: {ex}")
        if args.json:
            print(json.dumps({"status": "failed", "error": str(ex)}, indent=2, sort_keys=True))
        return 1

    summary = result.summary
    changed = int(summary.get("entries_renamed", 0))
    parse_errors = int(summary.get("parse_errors", 0))
    unresolved_targets = int(summary.get("unresolved_targets", 0))

    if args.json:
        print(result_to_json(result, detail_limit=max(1, args.detail_limit)))
    else:
        action = "applied" if args.write else "planned"
        print(f"key-normalize summary ({action}):")
        for key in sorted(summary):
            print(f"  {key}: {summary[key]}")

        if result.issue_counts:
            print("issue_counts:")
            for key in sorted(result.issue_counts):
                print(f"  {key}: {result.issue_counts[key]}")

        if result.changes:
            print("key_changes:")
            for change in result.changes[:25]:
                print(f"  {change.file_path} :: {change.old_key or '<missing>'} -> {change.new_key}")
            if len(result.changes) > 25:
                print(f"  ... and {len(result.changes) - 25} more")

    if args.fail_on_issues and (changed > 0 or parse_errors > 0 or unresolved_targets > 0):
        return 4
    return 0


def command_verify_orals(cfg: OpsConfig, recorder: RunRecorder, as_json: bool, fail_on_error: bool) -> int:
    files_scanned, entries_scanned, issues = run_verify_orals(cfg)
    write_issues(Path(cfg.db_path), recorder.run_id, issues)

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    payload = {
        "errors": error_count,
        "warnings": warning_count,
    }
    recorder.finish(
        status="ok" if error_count == 0 else "issues",
        files_scanned=files_scanned,
        entries_scanned=entries_scanned,
        issues_found=len(issues),
        payload=payload,
    )

    if as_json:
        print(
            json.dumps(
                {
                    "run_id": recorder.run_id,
                    "summary": payload,
                    "files_scanned": files_scanned,
                    "entries_scanned": entries_scanned,
                    "issues": [dataclasses.asdict(i) for i in issues],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        by_type: dict[str, int] = {}
        for issue in issues:
            by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1

        print(f"run_id: {recorder.run_id}")
        print(f"files_scanned: {files_scanned}")
        print(f"entries_scanned: {entries_scanned}")
        print(f"issues_found: {len(issues)}")
        print(f"errors: {error_count}")
        print(f"warnings: {warning_count}")
        if by_type:
            print("issues_by_type:")
            for k in sorted(by_type):
                print(f"  {k}: {by_type[k]}")

    if fail_on_error and error_count > 0:
        return 3
    return 0


def command_profile(cfg: OpsConfig, profile_path: Path) -> int:
    if not profile_path.exists():
        print(f"Profile not found: {profile_path}")
        return 1

    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    steps = data.get("steps")
    if not isinstance(steps, list):
        print("Invalid profile: expected `steps = [..]`")
        return 1

    for step in steps:
        step_name = ""
        step_payload: dict[str, object] = {}
        if isinstance(step, str):
            step_name = step
        elif isinstance(step, dict):
            raw_name = step.get("command")
            if isinstance(raw_name, str):
                step_name = raw_name.strip()
                step_payload = step
        if not step_name:
            print(f"Invalid profile step: {step!r}")
            return 1

        print(f"[profile] step: {step_name}")
        if step_name == "doctor":
            rc = command_doctor(cfg)
        elif step_name == "scan":
            recorder = RunRecorder(Path(cfg.db_path), command="scan")
            recorder.start()
            rc = command_scan(cfg, recorder, as_json=False)
        elif step_name == "lint":
            recorder = RunRecorder(Path(cfg.db_path), command="lint")
            recorder.start()
            rc = command_lint(cfg, recorder, as_json=False, fail_on_error=False)
        elif step_name == "verify-orals":
            recorder = RunRecorder(Path(cfg.db_path), command="verify-orals")
            recorder.start()
            rc = command_verify_orals(cfg, recorder, as_json=False, fail_on_error=False)
        elif step_name == "report":
            rc = command_report(cfg, run_id=None, as_json=False)
        elif step_name == "install-hooks":
            rc = command_install_hooks()
        elif step_name == "export-tracking":
            rc = command_export_tracking(cfg)
        elif step_name == "intake":
            targets_raw = step_payload.get("targets")
            targets: list[str] = []
            if isinstance(targets_raw, list):
                for target in targets_raw:
                    if isinstance(target, str) and target.strip():
                        targets.append(target.strip())
            if not targets:
                print("Profile intake step requires `targets = [\"venue:year\", ...]`")
                return 1
            mode = str(step_payload.get("mode", "plan")).strip().lower()
            if mode not in {"discover", "plan", "run"}:
                print(f"Unsupported intake mode in profile: {mode}")
                return 1
            max_records = 0
            if isinstance(step_payload.get("max_records"), int):
                max_records = max(0, int(step_payload["max_records"]))
            intake_args = argparse.Namespace(
                mode=mode,
                targets=targets,
                intake_config=str(step_payload.get("intake_config", "ops/intake-pipeline.toml")),
                max_records=max_records,
                write=bool(step_payload.get("write", False)),
                fail_on_gap=bool(step_payload.get("fail_on_gap", False)),
                out=str(step_payload.get("out", "")).strip() or None,
                json=bool(step_payload.get("json", False)),
            )
            rc = command_intake_pipeline(intake_args)
        elif step_name == "enrich":
            targets_raw = step_payload.get("targets")
            targets: list[str] = []
            if isinstance(targets_raw, list):
                for target in targets_raw:
                    if isinstance(target, str) and target.strip():
                        targets.append(target.strip())
            if not targets:
                print("Profile enrich step requires `targets = [\"file.bib\", ...]`")
                return 1
            mode = str(step_payload.get("mode", "run")).strip().lower()
            if mode not in {"plan", "run"}:
                print(f"Unsupported enrich mode in profile: {mode}")
                return 1
            max_entries = 0
            if isinstance(step_payload.get("max_entries"), int):
                max_entries = max(0, int(step_payload["max_entries"]))
            checkpoint_path = None
            raw_checkpoint = step_payload.get("checkpoint_path")
            if isinstance(raw_checkpoint, str) and raw_checkpoint.strip():
                checkpoint_path = raw_checkpoint.strip()
            enrich_args = argparse.Namespace(
                mode=mode,
                targets=targets,
                enrichment_config=str(step_payload.get("enrichment_config", "ops/enrichment-pipeline.toml")),
                entry_key=[],
                max_entries=max_entries,
                overwrite=bool(step_payload.get("overwrite", False)),
                write=bool(step_payload.get("write", False)),
                resume=bool(step_payload.get("resume", False)),
                checkpoint_path=checkpoint_path,
                fail_on_unresolved=bool(step_payload.get("fail_on_unresolved", False)),
                verbose_entry_log=bool(step_payload.get("verbose_entry_log", False)),
                progress_log=str(step_payload.get("progress_log", "")).strip() or None,
                json=bool(step_payload.get("json", False)),
            )
            rc = command_enrich_pipeline(enrich_args)
        elif step_name == "pdf-sync":
            targets_raw = step_payload.get("targets")
            targets: list[str] = []
            if isinstance(targets_raw, list):
                for target in targets_raw:
                    if isinstance(target, str) and target.strip():
                        targets.append(target.strip())
            if not targets:
                print("Profile pdf-sync step requires `targets = [\"file.bib\", ...]`")
                return 1

            host_interval: list[str] = []
            raw_host_interval = step_payload.get("host_interval")
            if isinstance(raw_host_interval, list):
                for item in raw_host_interval:
                    if isinstance(item, str) and item.strip():
                        host_interval.append(item.strip())

            pdf_sync_args = argparse.Namespace(
                targets=targets,
                base_dir=str(step_payload.get("base_dir", "/home/b/documents")),
                no_download=bool(step_payload.get("no_download", False)),
                no_fix=bool(step_payload.get("no_fix", False)),
                dry_run=bool(step_payload.get("dry_run", False)),
                no_verify_existing=bool(step_payload.get("no_verify_existing", False)),
                no_smart_url_derivation=bool(step_payload.get("no_smart_url_derivation", False)),
                max_entries=int(step_payload.get("max_entries", 0) or 0),
                max_attempts=int(step_payload.get("max_attempts", 6) or 6),
                timeout_connect=float(step_payload.get("timeout_connect", 10.0) or 10.0),
                timeout_read=float(step_payload.get("timeout_read", 90.0) or 90.0),
                max_attempt_wall_seconds=float(step_payload.get("max_attempt_wall_seconds", 240.0) or 240.0),
                max_pdf_size_mb=int(step_payload.get("max_pdf_size_mb", 300) or 300),
                backoff_base_seconds=float(step_payload.get("backoff_base_seconds", 1.0) or 1.0),
                backoff_max_seconds=float(step_payload.get("backoff_max_seconds", 180.0) or 180.0),
                backoff_jitter_seconds=float(step_payload.get("backoff_jitter_seconds", 0.4) or 0.4),
                host_min_interval_seconds=float(step_payload.get("host_min_interval_seconds", 0.8) or 0.8),
                host_interval=host_interval,
                checkpoint_path=str(step_payload.get("checkpoint_path", "ops/pdf-sync-checkpoint.json")),
                no_resume=bool(step_payload.get("no_resume", False)),
                retry_failures=bool(step_payload.get("retry_failures", False)),
                progress_log=str(step_payload.get("progress_log", "")).strip() or None,
                console_progress=bool(step_payload.get("console_progress", False)),
                checkpoint_flush_seconds=float(step_payload.get("checkpoint_flush_seconds", 20.0) or 20.0),
                max_consecutive_failures=int(step_payload.get("max_consecutive_failures", 50) or 50),
                user_agent=str(step_payload.get("user_agent", "bibops-pdf-sync/1.0") or "bibops-pdf-sync/1.0"),
                pdf_sync_policy=str(step_payload.get("pdf_sync_policy", "")).strip() or None,
                fail_on_error=bool(step_payload.get("fail_on_error", False)),
                json=bool(step_payload.get("json", False)),
            )
            rc = command_pdf_sync(pdf_sync_args)
        elif step_name == "key-normalize":
            targets_raw = step_payload.get("targets")
            targets: list[str] = []
            if isinstance(targets_raw, list):
                for target in targets_raw:
                    if isinstance(target, str) and target.strip():
                        targets.append(target.strip())
            if not targets:
                print("Profile key-normalize step requires `targets = [\"file.bib\", ...]`")
                return 1

            key_args = argparse.Namespace(
                targets=targets,
                write=bool(step_payload.get("write", False)),
                canonicalize_all=bool(step_payload.get("canonicalize_all", False)),
                max_entries=int(step_payload.get("max_entries", 0) or 0),
                global_scope=str(step_payload.get("global_scope", "targets")),
                fail_on_issues=bool(step_payload.get("fail_on_issues", False)),
                detail_limit=int(step_payload.get("detail_limit", 200) or 200),
                no_backup=bool(step_payload.get("no_backup", False)),
                rollback_dir=str(step_payload.get("rollback_dir", "ops/key-normalize-rollbacks")),
                json=bool(step_payload.get("json", False)),
            )
            rc = command_key_normalize(cfg, key_args)
        else:
            print(f"Unknown profile step: {step_name}")
            return 1

        if rc != 0:
            print(f"[profile] step failed: {step_name} (rc={rc})")
            return rc

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bibliography operations control-plane")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to bibops TOML config")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("db-init", help="Initialize ops tables in SQLite")
    sub.add_parser("doctor", help="Check environment and repo readiness")

    scan = sub.add_parser("scan", help="Index bibliography files and parse status")
    scan.add_argument("--json", action="store_true", help="Emit JSON output")

    lint = sub.add_parser("lint", help="Run full quality linting across bibliography")
    lint.add_argument("--json", action="store_true", help="Emit JSON output")
    lint.add_argument("--fail-on-error", action="store_true", help="Return non-zero on error severity issues")

    verify_orals = sub.add_parser("verify-orals", help="Validate derived oral subsets against canonical conference files")
    verify_orals.add_argument("--json", action="store_true", help="Emit JSON output")
    verify_orals.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return non-zero when oral verification finds errors",
    )

    report = sub.add_parser("report", help="Report latest or selected lint/scan run")
    report.add_argument("--run-id", help="Specific run ID")
    report.add_argument("--json", action="store_true", help="Emit JSON output")

    sub.add_parser("install-hooks", help="Install git hooks from hooks/")
    sub.add_parser("export-tracking", help="Export tracking database to tracking.json")

    enrich = sub.add_parser("enrich", help="Run modular enrichment pipeline for specific bibliography files")
    enrich.add_argument("mode", choices=["plan", "run"], help="Pipeline mode")
    enrich.add_argument("targets", nargs="+", help="BibTeX file(s) or glob(s)")
    enrich.add_argument(
        "--enrichment-config",
        default="ops/enrichment-pipeline.toml",
        help="Enrichment pipeline config path",
    )
    enrich.add_argument("--entry-key", action="append", default=[], help="Specific entry key to process (repeatable)")
    enrich.add_argument("--max-entries", type=int, default=0, help="Cap processed entries per file")
    enrich.add_argument("--overwrite", action="store_true", help="Allow non-protected field overwrites")
    enrich.add_argument("--write", action="store_true", help="Write approved updates (run mode only)")
    enrich.add_argument("--resume", action="store_true", help="Resume from checkpoint state (run mode only)")
    enrich.add_argument(
        "--checkpoint-path",
        help="Optional checkpoint file path (single target) or checkpoint directory (multi-target)",
    )
    enrich.add_argument(
        "--fail-on-unresolved",
        action="store_true",
        help="Return non-zero when unresolved decisions exist (run mode only)",
    )
    enrich.add_argument(
        "--verbose-entry-log",
        action="store_true",
        help="Print per-entry progress lines while running",
    )
    enrich.add_argument(
        "--progress-log",
        help="Optional JSONL path for per-entry progress events",
    )
    enrich.add_argument("--json", action="store_true", help="Emit JSON output")

    intake = sub.add_parser("intake", help="Run modular intake pipeline for venue/year targets")
    intake.add_argument("mode", choices=["discover", "plan", "run"], help="Pipeline mode")
    intake.add_argument("targets", nargs="+", help="Targets in venue:year format (e.g., iclr:2025)")
    intake.add_argument(
        "--intake-config",
        default="ops/intake-pipeline.toml",
        help="Intake pipeline config path",
    )
    intake.add_argument("--max-records", type=int, default=0, help="Cap source records per target")
    intake.add_argument("--write", action="store_true", help="Write merged target .bib files (run mode only)")
    intake.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Return non-zero when gaps/issues remain",
    )
    intake.add_argument("--out", help="Optional output JSON path")
    intake.add_argument("--json", action="store_true", help="Emit JSON output")

    pdf_sync = sub.add_parser("pdf-sync", help="Synchronize local PDFs for BibTeX entries")
    pdf_sync.add_argument("targets", nargs="+", help="BibTeX file(s) or glob(s)")
    pdf_sync.add_argument("--base-dir", default="/home/b/documents", help="Local PDF root directory")
    pdf_sync.add_argument("--no-download", action="store_true", help="Skip network downloads")
    pdf_sync.add_argument("--no-fix", action="store_true", help="Skip fixing existing file fields/paths")
    pdf_sync.add_argument("--dry-run", action="store_true", help="Preview actions without file/network writes")
    pdf_sync.add_argument(
        "--no-verify-existing",
        action="store_true",
        help="Do not validate existing PDF files before linking",
    )
    pdf_sync.add_argument(
        "--no-smart-url-derivation",
        action="store_true",
        help="Disable venue/domain-aware URL derivation",
    )
    pdf_sync.add_argument("--max-entries", type=int, default=0, help="Cap entries processed per file")
    pdf_sync.add_argument("--max-attempts", type=int, default=6, help="Max attempts per URL")
    pdf_sync.add_argument("--timeout-connect", type=float, default=10.0, help="Connect timeout in seconds")
    pdf_sync.add_argument("--timeout-read", type=float, default=90.0, help="Read timeout in seconds")
    pdf_sync.add_argument(
        "--max-attempt-wall-seconds",
        type=float,
        default=240.0,
        help="Hard wall-clock timeout for each download attempt (0 disables)",
    )
    pdf_sync.add_argument("--max-pdf-size-mb", type=int, default=300, help="Max allowed PDF size in MB")
    pdf_sync.add_argument(
        "--backoff-base-seconds",
        type=float,
        default=1.0,
        help="Base exponential backoff delay in seconds",
    )
    pdf_sync.add_argument(
        "--backoff-max-seconds",
        type=float,
        default=180.0,
        help="Max backoff delay in seconds",
    )
    pdf_sync.add_argument(
        "--backoff-jitter-seconds",
        type=float,
        default=0.4,
        help="Random jitter added to pacing/backoff in seconds",
    )
    pdf_sync.add_argument(
        "--host-min-interval-seconds",
        type=float,
        default=0.8,
        help="Default min delay between requests to the same host",
    )
    pdf_sync.add_argument(
        "--host-interval",
        action="append",
        default=[],
        help="Per-host min interval override in host=seconds format (repeatable)",
    )
    pdf_sync.add_argument(
        "--checkpoint-path",
        default="ops/pdf-sync-checkpoint.json",
        help="Checkpoint JSON path for resume/retry state",
    )
    pdf_sync.add_argument("--no-resume", action="store_true", help="Ignore checkpoint skip state")
    pdf_sync.add_argument(
        "--retry-failures",
        action="store_true",
        help="Retry checkpointed failed entries when resuming",
    )
    pdf_sync.add_argument("--progress-log", help="Optional JSONL progress log path")
    pdf_sync.add_argument(
        "--console-progress",
        action="store_true",
        help="Mirror progress events to stderr while running",
    )
    pdf_sync.add_argument(
        "--checkpoint-flush-seconds",
        type=float,
        default=20.0,
        help="Persist checkpoint at most this many seconds between entry updates (0 flushes every entry)",
    )
    pdf_sync.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=50,
        help="Abort run after this many consecutive entry failures",
    )
    pdf_sync.add_argument("--user-agent", default="bibops-pdf-sync/1.0", help="HTTP User-Agent value")
    pdf_sync.add_argument("--pdf-sync-policy", help="Optional TOML policy file for downloader tuning")
    pdf_sync.add_argument("--fail-on-error", action="store_true", help="Return non-zero on download failures")
    pdf_sync.add_argument("--json", action="store_true", help="Emit JSON output")

    key_norm = sub.add_parser("key-normalize", help="Validate and normalize BibTeX keys")
    key_norm.add_argument("targets", nargs="+", help="BibTeX file(s) or glob(s)")
    key_norm.add_argument("--write", action="store_true", help="Write normalized keys back to files")
    key_norm.add_argument(
        "--canonicalize-all",
        action="store_true",
        help="Rewrite all keys to canonical generated form, even when already valid",
    )
    key_norm.add_argument("--max-entries", type=int, default=0, help="Cap entries processed per file")
    key_norm.add_argument(
        "--global-scope",
        choices=["none", "targets", "config"],
        default="targets",
        help="Collision scope: none, only targets, or full config roots",
    )
    key_norm.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Return non-zero when key updates would be required or parse/unresolved issues exist",
    )
    key_norm.add_argument("--detail-limit", type=int, default=200, help="Max detailed changes/issues in output")
    key_norm.add_argument("--no-backup", action="store_true", help="Skip writing .backup files when --write")
    key_norm.add_argument(
        "--rollback-dir",
        default="ops/key-normalize-rollbacks",
        help="Rollback artifact directory for transactional write guardrails",
    )
    key_norm.add_argument("--json", action="store_true", help="Emit JSON output")

    profile = sub.add_parser("run-profile", help="Run declarative ops profile")
    profile.add_argument("--profile", required=True, help="Path to profile TOML")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    cfg = load_config(Path(args.config))

    db_path = Path(cfg.db_path)
    init_db(db_path)

    if args.command == "db-init":
        print(f"Initialized ops tables in {db_path}")
        return 0

    if args.command == "doctor":
        return command_doctor(cfg)

    if args.command == "report":
        return command_report(cfg, run_id=args.run_id, as_json=args.json)

    if args.command == "install-hooks":
        return command_install_hooks()

    if args.command == "export-tracking":
        return command_export_tracking(cfg)

    if args.command == "enrich":
        with run_lock():
            return command_enrich_pipeline(args)

    if args.command == "intake":
        with run_lock():
            return command_intake_pipeline(args)

    if args.command == "pdf-sync":
        with run_lock():
            return command_pdf_sync(args)

    if args.command == "key-normalize":
        with run_lock():
            return command_key_normalize(cfg, args)

    if args.command == "run-profile":
        with run_lock():
            return command_profile(cfg, Path(args.profile))

    if args.command == "scan":
        recorder = RunRecorder(Path(cfg.db_path), command="scan")
        recorder.start()
        with run_lock():
            try:
                return command_scan(cfg, recorder, as_json=args.json)
            except Exception:
                recorder.finish("failed", 0, 0, 0, {"traceback": traceback.format_exc()})
                raise

    if args.command == "lint":
        recorder = RunRecorder(Path(cfg.db_path), command="lint")
        recorder.start()
        with run_lock():
            try:
                return command_lint(cfg, recorder, as_json=args.json, fail_on_error=args.fail_on_error)
            except Exception:
                recorder.finish("failed", 0, 0, 0, {"traceback": traceback.format_exc()})
                raise

    if args.command == "verify-orals":
        recorder = RunRecorder(Path(cfg.db_path), command="verify-orals")
        recorder.start()
        with run_lock():
            try:
                return command_verify_orals(cfg, recorder, as_json=args.json, fail_on_error=args.fail_on_error)
            except Exception:
                recorder.finish("failed", 0, 0, 0, {"traceback": traceback.format_exc()})
                raise

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
