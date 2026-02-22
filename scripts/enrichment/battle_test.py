#!/usr/bin/env python3
"""Systematic battle tests for the enrichment pipeline on real workloads."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

REPO = Path(__file__).resolve().parents[2]


@dataclasses.dataclass
class ScenarioResult:
    name: str
    ok: bool
    command: str
    rc: int
    duration_s: float
    details: dict[str, object]
    stdout_tail: str
    stderr_tail: str


def run_cmd(cmd: list[str], timeout: int = 600) -> tuple[subprocess.CompletedProcess[str], float]:
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc, time.time() - start


def tail(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(proc.stdout)


def entry_field(path: Path, entry_key: str, field: str) -> str:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    db = bibtexparser.loads(path.read_text(encoding="utf-8"), parser=parser)
    for entry in db.entries:
        if str(entry.get("ID", "")) == entry_key:
            return str(entry.get(field, "")).strip()
    return ""


def record(
    results: list[ScenarioResult],
    name: str,
    cmd: list[str],
    proc: subprocess.CompletedProcess[str],
    duration: float,
    ok: bool,
    details: dict[str, object] | None = None,
) -> None:
    results.append(
        ScenarioResult(
            name=name,
            ok=ok,
            command=" ".join(shlex.quote(x) for x in cmd),
            rc=proc.returncode,
            duration_s=duration,
            details=details or {},
            stdout_tail=tail(proc.stdout),
            stderr_tail=tail(proc.stderr),
        )
    )


def run_battle_tests(mode: str) -> dict[str, object]:
    results: list[ScenarioResult] = []

    max_small = 20
    max_medium = 50
    max_large = 100
    if mode == "quick":
        max_medium = 20
        max_large = 40
    elif mode == "stress":
        max_medium = 100
        max_large = 200

    # 1) CLI help surfaces
    for name, cmd in [
        ("cli_help", ["python3", "scripts/enrich-pipeline.py", "--help"]),
        ("cli_plan_help", ["python3", "scripts/enrich-pipeline.py", "plan", "--help"]),
        ("cli_run_help", ["python3", "scripts/enrich-pipeline.py", "run", "--help"]),
        ("bibops_enrich_help", ["python3", "scripts/bibops.py", "enrich", "--help"]),
    ]:
        proc, dur = run_cmd(cmd)
        record(results, name, cmd, proc, dur, proc.returncode == 0)

    # 2) Planning coverage tests
    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "plan",
        "conferences/iclr/2024.bib",
        "--max-entries",
        str(max_medium),
        "--json",
    ]
    proc, dur = run_cmd(cmd)
    ok = False
    details: dict[str, object] = {}
    first_key = ""
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        files = payload.get("files", [])
        if isinstance(files, list) and files:
            entry = files[0]
            planned = int(entry.get("planned_entries", 0))
            details["planned_entries"] = planned
            items = entry.get("items", [])
            if isinstance(items, list) and items:
                first = items[0]
                first_key = str(first.get("entry_key", ""))
                details["first_entry_key"] = first_key
            ok = planned > 0
    record(results, "plan_iclr_2024", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "plan",
        "conferences/neurips/1987.bib",
        "--max-entries",
        str(max_medium),
        "--json",
    ]
    proc, dur = run_cmd(cmd)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        files = payload.get("files", [])
        if isinstance(files, list) and files:
            planned = int(files[0].get("planned_entries", -1))
            details["planned_entries"] = planned
            ok = planned > 0
    record(results, "plan_neurips_1987_supported", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "plan",
        "conferences/icml/2020.bib",
        "--max-entries",
        str(max_medium),
        "--json",
    ]
    proc, dur = run_cmd(cmd)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        files = payload.get("files", [])
        if isinstance(files, list) and files:
            planned = int(files[0].get("planned_entries", 0))
            details["planned_entries"] = planned
            ok = planned > 0
    record(results, "plan_icml_2020", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "plan",
        "conferences/iclr/2024.bib",
        "conferences/neurips/2024.bib",
        "--max-entries",
        str(max_small),
        "--json",
    ]
    proc, dur = run_cmd(cmd)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        files = payload.get("files", [])
        if isinstance(files, list) and len(files) == 2:
            plans = [int(f.get("planned_entries", 0)) for f in files]
            details["planned_entries"] = plans
            ok = all(p >= 0 for p in plans)
    record(results, "plan_multi_target", cmd, proc, dur, ok, details)

    # 3) Entry-key filtering
    if first_key:
        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "plan",
            "conferences/iclr/2024.bib",
            "--entry-key",
            first_key,
            "--json",
        ]
        proc, dur = run_cmd(cmd)
        ok = False
        details = {"entry_key": first_key}
        if proc.returncode == 0:
            payload = parse_json_output(proc)
            files = payload.get("files", [])
            if isinstance(files, list) and files:
                planned = int(files[0].get("planned_entries", -1))
                details["planned_entries"] = planned
                ok = planned in (0, 1)
        record(results, "plan_entry_key_existing", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "plan",
        "conferences/iclr/2024.bib",
        "--entry-key",
        "__definitely_missing_key__",
        "--json",
    ]
    proc, dur = run_cmd(cmd)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        files = payload.get("files", [])
        if isinstance(files, list) and files:
            planned = int(files[0].get("planned_entries", -1))
            details["planned_entries"] = planned
            ok = planned == 0
    record(results, "plan_entry_key_missing", cmd, proc, dur, ok, details)

    # 4) Dry-run execution tests
    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "run",
        "conferences/iclr/2024.bib",
        "--max-entries",
        str(max_medium),
        "--json",
    ]
    proc, dur = run_cmd(cmd, timeout=1800)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        f = payload["files"][0]
        details = {
            "planned_entries": f.get("planned_entries"),
            "proposed_entries": f.get("proposed_entries"),
            "updated_entries": f.get("updated_entries"),
            "unresolved_entries": f.get("unresolved_entries"),
        }
        ok = int(f.get("planned_entries", 0)) >= 0 and int(f.get("unresolved_entries", -1)) >= 0
    record(results, "run_iclr_2024_dry", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "run",
        "conferences/neurips/2024.bib",
        "--max-entries",
        str(max_large),
        "--json",
    ]
    proc, dur = run_cmd(cmd, timeout=1800)
    ok = False
    details = {}
    unresolved_path = ""
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        f = payload["files"][0]
        unresolved_path = str(f.get("unresolved_path") or "")
        details = {
            "planned_entries": f.get("planned_entries"),
            "proposed_entries": f.get("proposed_entries"),
            "updated_entries": f.get("updated_entries"),
            "unresolved_entries": f.get("unresolved_entries"),
            "unresolved_path": unresolved_path,
        }
        ok = int(f.get("planned_entries", 0)) > 0 and int(f.get("proposed_entries", 0)) >= 0
    record(results, "run_neurips_2024_dry", cmd, proc, dur, ok, details)

    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "run",
        "conferences/icml/2020.bib",
        "--max-entries",
        str(max_medium),
        "--json",
    ]
    proc, dur = run_cmd(cmd, timeout=1800)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        f = payload["files"][0]
        details = {
            "planned_entries": f.get("planned_entries"),
            "proposed_entries": f.get("proposed_entries"),
            "updated_entries": f.get("updated_entries"),
            "unresolved_entries": f.get("unresolved_entries"),
        }
        ok = int(f.get("planned_entries", 0)) > 0 and int(f.get("proposed_entries", 0)) >= 0
    record(results, "run_icml_2020_dry", cmd, proc, dur, ok, details)

    # 4b) NeurIPS stale URL recovery (single-key targeted check)
    neurips_file = (REPO / "conferences/neurips/2024.bib").read_text(encoding="utf-8")
    stale_candidates = [
        "zhang2024gliding",
        "tian2024reinforcement",
        "bai2024faster",
        "livni2024credit",
    ]
    stale_key = ""
    for candidate in stale_candidates:
        if f"@inproceedings{{{candidate}," in neurips_file:
            stale_key = candidate
            break

    if stale_key:
        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "run",
            "conferences/neurips/2024.bib",
            "--entry-key",
            stale_key,
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = False
        details = {"entry_key": stale_key}
        if proc.returncode == 0:
            payload = parse_json_output(proc)
            f = payload["files"][0]
            details.update(
                {
                    "planned_entries": f.get("planned_entries"),
                    "proposed_entries": f.get("proposed_entries"),
                    "unresolved_entries": f.get("unresolved_entries"),
                }
            )
            planned = int(f.get("planned_entries", 0))
            unresolved = int(f.get("unresolved_entries", 1))
            details["already_enriched"] = planned == 0
            ok = unresolved == 0 and (planned >= 1 or planned == 0)
        record(results, "neurips_stale_url_recovery", cmd, proc, dur, ok, details)
    else:
        cmd = ["echo", "neurips stale key candidate not present; skipping check"]
        fake = subprocess.CompletedProcess(cmd, 0, "skip", "")
        record(
            results,
            "neurips_stale_url_recovery",
            cmd,
            fake,
            0.0,
            True,
            {"skipped": True},
        )

    # 4c) ICML stale URL recovery (single-key targeted check on temp copy)
    with tempfile.TemporaryDirectory(prefix="enrich-icml-stale-") as td:
        tmp_root = Path(td)
        icml_copy = tmp_root / "icml2020-copy.bib"
        stale_key = "DBLP:conf:icml:0001AKP20"
        stale_url = "https://proceedings.mlr.press/v119/zzzzzzzzzzzzzzzz.html"

        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.loads((REPO / "conferences/icml/2020.bib").read_text(encoding="utf-8"), parser=parser)

        found = False
        for entry in db.entries:
            if str(entry.get("ID", "")) == stale_key:
                entry["url"] = stale_url
                entry.pop("pdf", None)
                entry.pop("abstract", None)
                found = True
                break

        writer = BibTexWriter()
        writer.indent = "  "
        writer.order_entries_by = None
        icml_copy.write_text(writer.write(db), encoding="utf-8")

        if found:
            before_url = entry_field(icml_copy, stale_key, "url")
            cmd = [
                "python3",
                "scripts/enrich-pipeline.py",
                "run",
                str(icml_copy),
                "--entry-key",
                stale_key,
                "--write",
                "--json",
            ]
            proc, dur = run_cmd(cmd, timeout=1800)
            ok = False
            details = {"entry_key": stale_key, "before_url": before_url}
            if proc.returncode == 0:
                payload = parse_json_output(proc)
                f = payload["files"][0]
                after_url = entry_field(icml_copy, stale_key, "url")
                after_pdf = entry_field(icml_copy, stale_key, "pdf")
                after_abstract = entry_field(icml_copy, stale_key, "abstract")
                details.update(
                    {
                        "planned_entries": f.get("planned_entries"),
                        "updated_entries": f.get("updated_entries"),
                        "unresolved_entries": f.get("unresolved_entries"),
                        "after_url": after_url,
                        "after_has_pdf": bool(after_pdf),
                        "after_has_abstract": bool(after_abstract),
                    }
                )
                ok = (
                    int(f.get("updated_entries", 0)) == 1
                    and int(f.get("unresolved_entries", 0)) == 0
                    and after_url != before_url
                    and "zzzzzzzzzzzzzzzz" not in after_url
                    and bool(after_pdf)
                    and bool(after_abstract)
                )
            record(results, "icml_stale_url_recovery", cmd, proc, dur, ok, details)
        else:
            cmd = ["echo", "icml stale key candidate not present; skipping check"]
            fake = subprocess.CompletedProcess(cmd, 0, "skip", "")
            record(
                results,
                "icml_stale_url_recovery",
                cmd,
                fake,
                0.0,
                True,
                {"skipped": True},
            )

    if unresolved_path:
        p = REPO / unresolved_path
        parse_ok = True
        line_count = 0
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    if not raw.strip():
                        continue
                    line_count += 1
                    try:
                        json.loads(raw)
                    except Exception:
                        parse_ok = False
                        break
        cmd = ["cat", unresolved_path]
        fake = subprocess.CompletedProcess(cmd, 0, "", "")
        record(
            results,
            "unresolved_queue_jsonl_valid",
            cmd,
            fake,
            0.0,
            parse_ok,
            {"line_count": line_count, "file_exists": p.exists()},
        )

    # 5) Wrapper parity
    cmd_direct = [
        "python3",
        "scripts/enrich-pipeline.py",
        "run",
        "conferences/iclr/2024.bib",
        "--max-entries",
        str(max_small),
        "--json",
    ]
    proc_direct, dur_direct = run_cmd(cmd_direct)
    cmd_wrap = [
        "python3",
        "scripts/bibops.py",
        "enrich",
        "run",
        "conferences/iclr/2024.bib",
        "--max-entries",
        str(max_small),
        "--json",
    ]
    proc_wrap, dur_wrap = run_cmd(cmd_wrap)
    ok = False
    details = {"direct_duration_s": round(dur_direct, 3), "wrapper_duration_s": round(dur_wrap, 3)}
    if proc_direct.returncode == 0 and proc_wrap.returncode == 0:
        a = parse_json_output(proc_direct)["files"][0]
        b = parse_json_output(proc_wrap)["files"][0]
        comparable = ["planned_entries", "proposed_entries", "updated_entries", "unresolved_entries"]
        details["direct"] = {k: a.get(k) for k in comparable}
        details["wrapper"] = {k: b.get(k) for k in comparable}
        ok = all(a.get(k) == b.get(k) for k in comparable)
    fake = subprocess.CompletedProcess(cmd_wrap, proc_wrap.returncode, proc_wrap.stdout, proc_wrap.stderr)
    record(results, "wrapper_parity_iclr_run", cmd_wrap, fake, dur_wrap, ok, details)

    # 6) Write-mode safety on temp copies
    with tempfile.TemporaryDirectory(prefix="enrich-battle-") as td:
        tmp_root = Path(td)
        iclr_copy = tmp_root / "iclr2024-copy.bib"
        neurips_copy = tmp_root / "neurips2024-copy.bib"
        iclr_copy.write_text((REPO / "conferences/iclr/2024.bib").read_text(encoding="utf-8"), encoding="utf-8")
        neurips_copy.write_text((REPO / "conferences/neurips/2024.bib").read_text(encoding="utf-8"), encoding="utf-8")

        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "run",
            str(iclr_copy),
            "--max-entries",
            str(max_small),
            "--write",
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = False
        details = {}
        if proc.returncode == 0:
            f = parse_json_output(proc)["files"][0]
            details = {
                "updated_entries": f.get("updated_entries"),
                "written": f.get("written"),
                "proposed_entries": f.get("proposed_entries"),
            }
            ok = bool(f.get("written"))
        record(results, "write_mode_iclr_copy", cmd, proc, dur, ok, details)

        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "run",
            str(neurips_copy),
            "--max-entries",
            str(max_small),
            "--write",
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = False
        details = {}
        if proc.returncode == 0:
            f = parse_json_output(proc)["files"][0]
            details = {
                "updated_entries": f.get("updated_entries"),
                "written": f.get("written"),
                "proposed_entries": f.get("proposed_entries"),
            }
            ok = bool(f.get("written"))
        record(results, "write_mode_neurips_copy", cmd, proc, dur, ok, details)

    # 7) Poisoned cache recovery and purge behavior (real key, isolated cache file)
    with tempfile.TemporaryDirectory(prefix="enrich-poison-cache-") as td:
        tmp_root = Path(td)
        iclr_copy = tmp_root / "iclr2017-copy.bib"
        key = "DBLP:conf:iclr:CohenW17"
        source_url = "https://openreview.net/forum?id=rJQKYt5ll"
        cache_path = tmp_root / "source-cache.json"
        runs_dir = tmp_root / "runs"
        triage_dir = tmp_root / "triage"
        cfg_path = tmp_root / "cfg.toml"

        iclr_copy.write_text((REPO / "conferences/iclr/2017.bib").read_text(encoding="utf-8"), encoding="utf-8")

        # Inject a known poisoned row that previously caused abstract skip.
        poisoned_payload = {
            "version": 1,
            "responses": {
                source_url: {
                    "status_code": 200,
                    "fetched_at": "2026-02-21T00:00:00+00:00",
                    "text": (
                        "<html><body><h1>Error</h1>"
                        "<pre>Too many requests: You have made 82 requests, "
                        "surpassing the limit of 60 requests. Please try again in 18 seconds.</pre>"
                        "</body></html>"
                    ),
                }
            },
        }
        cache_path.write_text(json.dumps(poisoned_payload, indent=2, sort_keys=True), encoding="utf-8")

        cfg_path.write_text(
            f"""
[defaults]
overwrite_existing = false
min_abstract_words = 25
allow_abstract_prefix_match = false
report_dir = "{runs_dir.as_posix()}"
triage_dir = "{triage_dir.as_posix()}"
source_cache_path = "{cache_path.as_posix()}"
timeout_seconds = 20
max_retries = 2
max_validation_retries = 4
host_min_interval_seconds = 1.0
backoff_base_seconds = 1.0
backoff_max_seconds = 30.0
user_agent = "bibliography-enrichment-pipeline/1.0"

[targets]
inproceedings = ["url", "pdf", "abstract", "doi"]

[policy]
protected_fields = ["author", "title", "booktitle", "year"]

[[venues]]
name = "iclr"
path_contains = "conferences/iclr/"
adapter = "openreview"
allowed_domains = ["openreview.net"]
""".strip(),
            encoding="utf-8",
        )

        before_abs = entry_field(iclr_copy, key, "abstract")
        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "--config",
            str(cfg_path),
            "run",
            str(iclr_copy),
            "--entry-key",
            key,
            "--write",
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = False
        details = {"entry_key": key, "before_has_abstract": bool(before_abs)}
        if proc.returncode == 0:
            payload = parse_json_output(proc)
            f = payload["files"][0]
            after_abs = entry_field(iclr_copy, key, "abstract")
            cache_json = json.loads(cache_path.read_text(encoding="utf-8"))
            row = (cache_json.get("responses") or {}).get(source_url, {})
            cached_text = str(row.get("text", ""))
            details.update(
                {
                    "updated_entries": f.get("updated_entries"),
                    "written": f.get("written"),
                    "after_has_abstract": bool(after_abs),
                    "after_abstract_len": len(after_abs),
                    "cache_row_has_too_many_requests": "too many requests" in cached_text.lower(),
                    "cache_row_has_citation_title": 'name="citation_title"' in cached_text.lower(),
                }
            )
            ok = (
                int(f.get("updated_entries", 0)) == 1
                and bool(f.get("written"))
                and bool(after_abs)
                and "too many requests" not in cached_text.lower()
                and 'name="citation_title"' in cached_text.lower()
            )
        record(results, "poisoned_cache_recovery_openreview", cmd, proc, dur, ok, details)

    # 8) fail-on-unresolved behavior
    with tempfile.TemporaryDirectory(prefix="enrich-battle-config-") as td:
        strict_cfg = Path(td) / "strict.toml"
        strict_cfg.write_text(
            """
[defaults]
overwrite_existing = true
min_abstract_words = 10000
allow_abstract_prefix_match = false
report_dir = "ops/enrichment-runs"
triage_dir = "ops/unresolved/enrichment"
source_cache_path = "ops/enrichment-source-cache.json"
timeout_seconds = 20
max_retries = 2
max_validation_retries = 4
host_min_interval_seconds = 1.0
backoff_base_seconds = 1.0
backoff_max_seconds = 30.0
user_agent = "bibliography-enrichment-pipeline/1.0"

[targets]
inproceedings = ["url", "pdf", "abstract"]

[policy]
protected_fields = ["author", "title", "booktitle", "year"]

[[venues]]
name = "iclr"
path_contains = "conferences/iclr/"
adapter = "openreview"
allowed_domains = ["example.com"]
""".strip(),
            encoding="utf-8",
        )

        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "--config",
            str(strict_cfg),
            "run",
            "conferences/iclr/2024.bib",
            "--max-entries",
            "1",
            "--fail-on-unresolved",
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = proc.returncode == 2
        details = {"expected_rc": 2, "actual_rc": proc.returncode}
        record(results, "fail_on_unresolved_rc", cmd, proc, dur, ok, details)

    # 9) Exception-ledger handling for known irrecoverable entries
    cmd = [
        "python3",
        "scripts/enrich-pipeline.py",
        "run",
        "conferences/icml/2020.bib",
        "--entry-key",
        "DBLP:conf:icml:Wei20",
        "--json",
    ]
    proc, dur = run_cmd(cmd, timeout=1800)
    ok = False
    details = {}
    if proc.returncode == 0:
        payload = parse_json_output(proc)
        f = payload["files"][0]
        report_path = Path(str(f.get("report_path", "")))
        details = {
            "planned_entries": f.get("planned_entries"),
            "unresolved_entries": f.get("unresolved_entries"),
            "skipped_entries": f.get("skipped_entries"),
        }
        if report_path.exists():
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            decision = next(
                (d for d in rep.get("decisions", []) if d.get("entry_key") == "DBLP:conf:icml:Wei20"),
                None,
            )
            reasons = decision.get("reasons", []) if isinstance(decision, dict) else []
            details["decision_reasons"] = reasons
            ok = (
                int(f.get("planned_entries", 0)) == 1
                and int(f.get("unresolved_entries", 1)) == 0
                and int(f.get("skipped_entries", 0)) == 1
                and any("exception ledger skip:" in str(r).lower() for r in reasons)
            )
    record(results, "exception_ledger_icml_wei20", cmd, proc, dur, ok, details)

    # 10) Resume checkpoint skip behavior
    with tempfile.TemporaryDirectory(prefix="enrich-resume-") as td:
        tmp_root = Path(td)
        src = REPO / "conferences/icml/2020.bib"
        copy = tmp_root / "icml2020-copy.bib"
        copy.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        checkpoint = tmp_root / "checkpoint.json"
        key = "DBLP:conf:icml:0001AKP20"
        base_sha = hashlib.sha256(copy.read_bytes()).hexdigest()
        checkpoint.write_text(
            json.dumps(
                {
                    "version": 1,
                    "file_path": str(copy),
                    "base_file_sha256": base_sha,
                    "completed_success_keys": [key],
                    "applied_updates_by_key": {},
                    "last_successful_key": key,
                    "updated_at": "2026-01-01T00:00:00+00:00",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        cmd = [
            "python3",
            "scripts/enrich-pipeline.py",
            "run",
            str(copy),
            "--entry-key",
            key,
            "--resume",
            "--checkpoint-path",
            str(checkpoint),
            "--json",
        ]
        proc, dur = run_cmd(cmd, timeout=1800)
        ok = False
        details = {}
        if proc.returncode == 0:
            payload = parse_json_output(proc)
            f = payload["files"][0]
            details = {
                "planned_entries": f.get("planned_entries"),
                "proposed_entries": f.get("proposed_entries"),
                "unresolved_entries": f.get("unresolved_entries"),
                "checkpoint_removed": not checkpoint.exists(),
            }
            ok = (
                int(f.get("planned_entries", 1)) == 0
                and int(f.get("proposed_entries", 1)) == 0
                and int(f.get("unresolved_entries", 1)) == 0
                and not checkpoint.exists()
            )
        record(results, "resume_checkpoint_skip", cmd, proc, dur, ok, details)

    # 11) Circuit breaker behavior for repeated transient host failures
    cmd = [
        "python3",
        "-c",
        (
            "from pathlib import Path; "
            "from scripts.enrichment.http_client import CachedHttpClient; "
            "c=CachedHttpClient(timeout_seconds=1,max_retries=0,max_validation_retries=0,"
            "backoff_base_seconds=0.1,backoff_max_seconds=0.2,user_agent='test',"
            "cache_path=Path('/tmp/enrich-cb-cache.json'),host_min_interval=0.0,"
            "host_circuit_breaker_threshold=1,host_circuit_breaker_cooldown_seconds=60.0); "
            "u='http://127.0.0.1:9/nope'; c.get_text(u,use_cache=False); c.get_text(u,use_cache=False); "
            "s=c.stats(); c.close(); "
            "import sys; sys.exit(0 if int(s.get('circuit_breaker_trips',0))>=1 and "
            "int(s.get('circuit_breaker_short_circuits',0))>=1 else 1)"
        ),
    ]
    proc, dur = run_cmd(cmd, timeout=120)
    record(results, "circuit_breaker_trips", cmd, proc, dur, proc.returncode == 0)

    # 12) Transactional write guard catches parse/integrity regressions
    cmd = [
        "bash",
        "-lc",
        (
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "import tempfile\n"
            "from scripts.enrichment.bibtex_io import (\n"
            "    BibWriteIntegrityError,\n"
            "    parse_bib_text,\n"
            "    transactional_write_bib_file,\n"
            ")\n"
            "\n"
            "text = \"\"\"@inproceedings{k,\n"
            "  author={A},\n"
            "  title={T},\n"
            "  booktitle={ICML},\n"
            "  year={2020},\n"
            "  abstract={bad \\\\{ text}\n"
            "}\n"
            "\"\"\"\n"
            "ok = False\n"
            "with tempfile.TemporaryDirectory(prefix='enrich-write-guard-') as td:\n"
            "    p = Path(td) / 'x.bib'\n"
            "    p.write_text(text, encoding='utf-8')\n"
            "    db = parse_bib_text(text)\n"
            "    try:\n"
            "        transactional_write_bib_file(\n"
            "            p,\n"
            "            db,\n"
            "            baseline_entries=1,\n"
            "            baseline_comments=0,\n"
            "            max_comment_increase=0,\n"
            "            rollback_dir=Path(td) / 'roll',\n"
            "        )\n"
            "    except BibWriteIntegrityError as e:\n"
            "        ok = 'rollback_original=' in str(e) and 'rollback_candidate=' in str(e)\n"
            "raise SystemExit(0 if ok else 1)\n"
            "PY"
        ),
    ]
    proc, dur = run_cmd(cmd, timeout=120)
    record(results, "transactional_write_guard", cmd, proc, dur, proc.returncode == 0)

    # 13) Makefile command surfaces
    for name, cmd in [
        ("make_enrich_plan", ["make", "enrich-plan", "FILE=conferences/iclr/2024.bib"]),
        ("make_enrich_run", ["make", "enrich-run", "FILE=conferences/iclr/2024.bib"]),
    ]:
        proc, dur = run_cmd(cmd, timeout=1800)
        record(results, name, cmd, proc, dur, proc.returncode == 0)

    # 14) Optional heavy end-to-end health check
    if mode == "stress":
        cmd = ["python3", "scripts/bibops.py", "lint", "--fail-on-error"]
        proc, dur = run_cmd(cmd, timeout=3600)
        record(results, "bibops_lint_fail_on_error", cmd, proc, dur, proc.returncode == 0)

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    report = {
        "mode": mode,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "total_duration_s": round(sum(r.duration_s for r in results), 3),
        },
        "results": [dataclasses.asdict(r) for r in results],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Battle-test enrichment pipeline")
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "stress"],
        default="standard",
        help="Test intensity",
    )
    parser.add_argument(
        "--out",
        default="ops/enrichment-runs/battle-test-report.json",
        help="Report output path",
    )
    args = parser.parse_args()

    report = run_battle_tests(args.mode)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"report: {out}")

    return 0 if report["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
