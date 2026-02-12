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
import uuid
from pathlib import Path
from typing import Iterable

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

DEFAULT_CONFIG_PATH = Path("ops/bibops.toml")
DEFAULT_DB_PATH = Path("bibliography.db")
LOCK_PATH = Path("ops/.bibops.lock")


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
            "curated",
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
    value = (value or "").replace("{", "").replace("}", "").lower().strip()
    return re.sub(r"\s+", " ", value)


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
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    with path.open("r", encoding="utf-8") as f:
        return bibtexparser.load(f, parser=parser)


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
                    raise RuntimeError(f"Another bibops process is running (pid={pid})")
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
    m = re.search(r"(19|20)\d{2}", key)
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

    for file_path, rows in by_file.items():
        local_key_map: dict[str, list[EntryResult]] = {}
        local_title_map: dict[str, list[EntryResult]] = {}

        for r in rows:
            local_key_map.setdefault(r.entry_key, []).append(r)
            if r.title_norm:
                local_title_map.setdefault(r.title_norm, []).append(r)

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

        for t, ts in local_title_map.items():
            if len(ts) > 1:
                add_issue(
                    Issue(
                        file_path=file_path,
                        entry_key=ts[0].entry_key,
                        issue_type="duplicate_title_in_file",
                        severity="warning",
                        message="Duplicate normalized title in file",
                        details={"title": t, "count": str(len(ts))},
                    )
                )

    for k, rows in by_key_global.items():
        file_set = {r.file_path for r in rows}
        if k and len(file_set) > 1:
            add_issue(
                Issue(
                    file_path="*",
                    entry_key=k,
                    issue_type="duplicate_key_global",
                    severity="warning",
                    message="Key appears in multiple files",
                    details={"files": ", ".join(sorted(file_set))},
                )
            )

    for r in entry_rows:
        key = r.entry_key
        entry_type = r.entry_type.lower()
        year = r.year

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


def command_doctor(cfg: OpsConfig) -> int:
    problems: list[str] = []

    if shutil.which("guix") is None:
        problems.append("guix not found in PATH")

    if not Path(cfg.db_path).exists():
        print(f"INFO: database not found at {cfg.db_path}; will be created on first run")

    if not Path("hooks/pre-commit").exists() or not Path("hooks/commit-msg").exists():
        problems.append("versioned hooks missing under hooks/")

    if not Path("scripts/install-hooks.py").exists():
        problems.append("scripts/install-hooks.py missing")

    discovered = discover_bib_files(cfg)
    if not discovered:
        problems.append("no .bib files discovered from configured roots")

    if problems:
        print("doctor: FAILED")
        for p in problems:
            print(f"- {p}")
        return 2

    print("doctor: OK")
    print(f"- discovered_bib_files: {len(discovered)}")
    print(f"- db_path: {cfg.db_path}")
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
    issues = scan_issues + lint_issues

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


def command_profile(cfg: OpsConfig, profile_path: Path) -> int:
    if not profile_path.exists():
        print(f"Profile not found: {profile_path}")
        return 1

    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    steps = data.get("steps")
    if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
        print("Invalid profile: expected `steps = [..]`")
        return 1

    for step in steps:
        print(f"[profile] step: {step}")
        if step == "doctor":
            rc = command_doctor(cfg)
        elif step == "scan":
            recorder = RunRecorder(Path(cfg.db_path), command="scan")
            recorder.start()
            rc = command_scan(cfg, recorder, as_json=False)
        elif step == "lint":
            recorder = RunRecorder(Path(cfg.db_path), command="lint")
            recorder.start()
            rc = command_lint(cfg, recorder, as_json=False, fail_on_error=False)
        elif step == "report":
            rc = command_report(cfg, run_id=None, as_json=False)
        elif step == "install-hooks":
            rc = command_install_hooks()
        elif step == "export-tracking":
            rc = command_export_tracking(cfg)
        else:
            print(f"Unknown profile step: {step}")
            return 1

        if rc != 0:
            print(f"[profile] step failed: {step} (rc={rc})")
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

    report = sub.add_parser("report", help="Report latest or selected lint/scan run")
    report.add_argument("--run-id", help="Specific run ID")
    report.add_argument("--json", action="store_true", help="Emit JSON output")

    sub.add_parser("install-hooks", help="Install git hooks from hooks/")
    sub.add_parser("export-tracking", help="Export tracking database to tracking.json")

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
