from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any

import bibtexparser

from core.bibtex_io import parse_bib_file, parse_bib_text, write_bib_file
from core.http_client import CachedHttpClient
from core.normalization import normalize_text, sanitize_bibtex_text
from core.time_utils import now_iso

from .config import IntakeConfig, VenuePolicy
from .keygen import generate_bib_key
from .models import (
    CatalogSnapshot,
    IntakeIssue,
    IntakeRecord,
    IntakeRunEnvelope,
    IntakeSummary,
    IntakeTarget,
    new_run_id,
)
from .sources import build_catalog_adapter_registry
from .sources.base import CatalogContext


class IntakeEngine:
    def __init__(self, cfg: IntakeConfig):
        self.cfg = cfg
        self.http_client = CachedHttpClient(
            timeout_seconds=cfg.timeout_seconds,
            max_retries=cfg.max_retries,
            max_validation_retries=cfg.max_validation_retries,
            backoff_base_seconds=cfg.backoff_base_seconds,
            backoff_max_seconds=cfg.backoff_max_seconds,
            user_agent=cfg.user_agent,
            cache_path=cfg.source_cache_path,
            host_min_interval=cfg.host_min_interval_seconds,
            host_min_interval_by_host=cfg.host_min_interval_by_host,
            host_circuit_breaker_threshold=cfg.host_circuit_breaker_threshold,
            host_circuit_breaker_cooldown_seconds=cfg.host_circuit_breaker_cooldown_seconds,
        )
        self.adapters = build_catalog_adapter_registry(self.http_client)

    def close(self) -> None:
        self.http_client.close()

    def _resolve_policy(self, venue: str) -> VenuePolicy:
        policy = self.cfg.venue(venue)
        if policy is None:
            raise KeyError(f"unknown venue `{venue}`")
        return policy

    def _target_with_binding(self, policy: VenuePolicy, year: int, index: int) -> IntakeTarget:
        binding = policy.adapters[index]
        params: dict[str, Any] = dict(binding.params)
        if policy.default_booktitle and "booktitle" not in params:
            params["booktitle"] = policy.default_booktitle
        if policy.default_publisher and "publisher" not in params:
            params["publisher"] = policy.default_publisher
        return IntakeTarget(
            venue=policy.name,
            year=year,
            file_path=policy.file_path_template.format(year=year, venue=policy.name),
            adapter=binding.name,
            params=params,
        )

    def discover(
        self,
        venue: str,
        year: int,
        *,
        purpose: str = "plan",
        max_records: int = 0,
    ) -> tuple[CatalogSnapshot | None, list[dict[str, str]]]:
        policy = self._resolve_policy(venue)
        attempts: list[dict[str, str]] = []
        for idx, binding in enumerate(policy.adapters):
            target = self._target_with_binding(policy, year, idx)
            adapter = self.adapters.get(binding.name)
            if adapter is None:
                attempts.append({"adapter": binding.name, "status": "missing_adapter"})
                continue
            snapshot = adapter.fetch_catalog(
                CatalogContext(
                    target=target,
                    purpose=purpose,
                    max_records=max(0, int(max_records)),
                )
            )
            if snapshot is None or not snapshot.records:
                attempts.append({"adapter": binding.name, "status": "empty"})
                continue
            attempts.append({"adapter": binding.name, "status": "selected"})
            return snapshot, attempts
        return None, attempts

    @staticmethod
    def _validate_record(record: IntakeRecord) -> list[str]:
        errors: list[str] = []
        if not record.source_id:
            errors.append("missing source_id")
        if not record.title:
            errors.append("missing title")
        if not record.authors:
            errors.append("missing authors")
        if not record.booktitle:
            errors.append("missing booktitle")
        if int(record.year) < 1900:
            errors.append("invalid year")
        return errors

    @staticmethod
    def _sort_records(records: list[IntakeRecord]) -> list[IntakeRecord]:
        return sorted(records, key=lambda r: (normalize_text(r.title), r.source_id))

    def _entry_from_record(
        self,
        record: IntakeRecord,
        adapter_name: str,
        existing_entry: dict[str, Any] | None,
        existing_keys: set[str],
    ) -> dict[str, Any]:
        key = ""
        if existing_entry is not None:
            key = str(existing_entry.get("ID", "")).strip()
        if not key:
            first_author = record.authors[0] if record.authors else "paper"
            key = generate_bib_key(first_author=first_author, year=record.year, title=record.title, existing_keys=existing_keys)
        elif key not in existing_keys:
            existing_keys.add(key)

        entry: dict[str, Any] = {}
        if existing_entry is not None:
            for field, value in existing_entry.items():
                if field in {"ID", "ENTRYTYPE"}:
                    continue
                entry[field] = value

        entry["ENTRYTYPE"] = "inproceedings"
        entry["ID"] = key
        entry["author"] = " and ".join(record.authors)
        entry["title"] = sanitize_bibtex_text(record.title)
        entry["booktitle"] = sanitize_bibtex_text(record.booktitle)
        entry["year"] = str(int(record.year))

        if record.publisher:
            entry["publisher"] = sanitize_bibtex_text(record.publisher)
        if record.url:
            entry["url"] = record.url
        else:
            entry.pop("url", None)
        if record.pdf:
            entry["pdf"] = record.pdf
        else:
            entry.pop("pdf", None)
        if record.abstract:
            entry["abstract"] = sanitize_bibtex_text(record.abstract)
        else:
            entry.pop("abstract", None)
        if record.doi:
            entry["doi"] = record.doi
        else:
            entry.pop("doi", None)
        if record.note:
            entry["note"] = sanitize_bibtex_text(record.note)
        entry["sourceid"] = f"{adapter_name}:{record.source_id}"
        for field, value in sorted(record.extra_fields.items()):
            if not field or field in {"ID", "ENTRYTYPE"}:
                continue
            if field in entry:
                continue
            if value:
                entry[field] = value
        return entry

    def _load_existing(self, file_path: Path) -> bibtexparser.bibdatabase.BibDatabase | None:
        if not file_path.exists():
            return None
        return parse_bib_file(file_path)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True))
                handle.write("\n")

    def _write_snapshot(self, snapshot: CatalogSnapshot, run_id: str) -> Path:
        path = self.cfg.snapshot_dir / f"{snapshot.target.venue}-{snapshot.target.year}-{run_id}.json"
        payload = {
            "adapter": snapshot.adapter,
            "target": dataclasses.asdict(snapshot.target),
            "fetched_at": snapshot.fetched_at,
            "expected_count": snapshot.expected_count,
            "metadata": snapshot.metadata,
            "records": [dataclasses.asdict(record) for record in snapshot.records],
        }
        self._write_json(path, payload)
        return path

    def run_target(
        self,
        venue: str,
        year: int,
        *,
        write: bool,
        fail_on_gap: bool,
        max_records: int = 0,
        run_id: str | None = None,
    ) -> tuple[IntakeSummary, list[IntakeIssue]]:
        this_run_id = run_id or new_run_id()
        started = now_iso()
        issues: list[IntakeIssue] = []

        snapshot, attempts = self.discover(
            venue,
            year,
            purpose="run" if write else "plan",
            max_records=max_records,
        )
        if snapshot is None:
            message = "no source adapter produced records"
            issues.append(
                IntakeIssue(
                    severity="error",
                    code="catalog_empty",
                    message=message,
                    details={"attempts": json.dumps(attempts, sort_keys=True)},
                )
            )
            summary = IntakeSummary(
                target=f"{venue}:{year}",
                adapter="",
                file_path=str(Path(f"conferences/{venue}/{year}.bib")),
                source_count=0,
                existing_count=0,
                matched_count=0,
                missing_count=0,
                extra_count=0,
                duplicate_source_count=0,
                invalid_record_count=0,
                written=False,
                report_path="",
                unresolved_path=None,
                snapshot_path=None,
            )
            return summary, issues

        if max_records > 0 and len(snapshot.records) > max_records:
            snapshot.records = snapshot.records[:max_records]
            if snapshot.expected_count is not None:
                snapshot.expected_count = min(snapshot.expected_count, max_records)

        snapshot_path = self._write_snapshot(snapshot, this_run_id)
        file_path = Path(snapshot.target.file_path)
        adapter = self.adapters[snapshot.adapter]
        existing_db = self._load_existing(file_path)

        existing_comments = []
        existing_entries: list[dict[str, Any]] = []
        if existing_db is not None:
            existing_comments = list(existing_db.comments)
            existing_entries = list(existing_db.entries)

        existing_by_source: dict[str, dict[str, Any]] = {}
        unresolved_existing = 0
        for entry in existing_entries:
            source_id = adapter.source_id_from_entry(entry)
            if not source_id:
                unresolved_existing += 1
                continue
            if source_id in existing_by_source:
                issues.append(
                    IntakeIssue(
                        severity="warning",
                        code="existing_duplicate_source_id",
                        message="multiple existing entries map to same source id",
                        source_id=source_id,
                        entry_key=str(entry.get("ID", "")).strip() or None,
                    )
                )
                continue
            existing_by_source[source_id] = entry

        source_by_id: dict[str, IntakeRecord] = {}
        duplicate_source_count = 0
        invalid_record_count = 0
        for record in self._sort_records(snapshot.records):
            if record.source_id in source_by_id:
                duplicate_source_count += 1
                issues.append(
                    IntakeIssue(
                        severity="error",
                        code="duplicate_source_id",
                        message="source record id duplicated in upstream catalog",
                        source_id=record.source_id,
                    )
                )
                continue
            validation_errors = self._validate_record(record)
            if validation_errors:
                invalid_record_count += 1
                issues.append(
                    IntakeIssue(
                        severity="error",
                        code="invalid_source_record",
                        message="; ".join(validation_errors),
                        source_id=record.source_id or None,
                    )
                )
                continue
            source_by_id[record.source_id] = record

        source_ids = set(source_by_id)
        existing_ids = set(existing_by_source)
        matched_ids = source_ids & existing_ids
        missing_ids = source_ids - existing_ids
        extra_ids = existing_ids - source_ids
        pre_existing_count = len(existing_by_source)
        pre_matched_count = len(matched_ids)
        pre_missing_count = len(missing_ids)
        pre_extra_count = len(extra_ids)

        summary_existing_count = pre_existing_count
        summary_matched_count = pre_matched_count
        summary_missing_count = pre_missing_count
        summary_extra_count = pre_extra_count
        post_write_verified = False

        if not write:
            for source_id in sorted(missing_ids):
                issues.append(
                    IntakeIssue(
                        severity="warning",
                        code="missing_existing_entry",
                        message="source paper missing from current file",
                        source_id=source_id,
                    )
                )
            for source_id in sorted(extra_ids):
                issues.append(
                    IntakeIssue(
                        severity="warning",
                        code="extra_existing_entry",
                        message="entry exists locally but not in current source snapshot",
                        source_id=source_id,
                        entry_key=str(existing_by_source[source_id].get("ID", "")).strip() or None,
                    )
                )
        elif extra_ids:
            issues.append(
                IntakeIssue(
                    severity="info",
                    code="extra_existing_entries_pruned",
                    message=f"{len(extra_ids)} existing entries not found in source and will be pruned on write",
                )
            )
        if unresolved_existing:
            issues.append(
                IntakeIssue(
                    severity="warning",
                    code="existing_without_source_id",
                    message=f"{unresolved_existing} existing entries could not be mapped to source ids",
                )
            )

        write_error: str | None = None
        wrote = False

        if write:
            block_write = any(issue.severity == "error" for issue in issues)
            if block_write:
                write_error = "write blocked due to unresolved intake issues"
            else:
                existing_keys: set[str] = set()
                for entry in existing_entries:
                    key = str(entry.get("ID", "")).strip()
                    if key:
                        existing_keys.add(key)

                built_entries: list[dict[str, Any]] = []
                for source_id in sorted(source_by_id):
                    record = source_by_id[source_id]
                    existing = existing_by_source.get(source_id)
                    built_entries.append(
                        self._entry_from_record(
                            record=record,
                            adapter_name=snapshot.adapter,
                            existing_entry=existing,
                            existing_keys=existing_keys,
                        )
                    )

                db = bibtexparser.bibdatabase.BibDatabase()
                db.entries = sorted(
                    built_entries,
                    key=lambda e: (normalize_text(str(e.get("title", ""))), str(e.get("ID", ""))),
                )
                db.comments = existing_comments

                file_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    suffix=".bib",
                    prefix=f"{file_path.stem}-",
                    dir=str(file_path.parent),
                    delete=False,
                ) as temp:
                    temp_path = Path(temp.name)
                try:
                    write_bib_file(temp_path, db)
                    parse_bib_text(temp_path.read_text(encoding="utf-8"))
                    temp_path.replace(file_path)
                    wrote = True
                except Exception as exc:
                    write_error = str(exc)
                    temp_path.unlink(missing_ok=True)

        if write and wrote:
            try:
                written_db = self._load_existing(file_path)
                if written_db is None:
                    raise RuntimeError("written bib file missing after write")

                written_by_source: dict[str, dict[str, Any]] = {}
                unresolved_written = 0
                duplicate_written = 0
                for entry in written_db.entries:
                    source_id = adapter.source_id_from_entry(entry)
                    if not source_id:
                        unresolved_written += 1
                        continue
                    if source_id in written_by_source:
                        duplicate_written += 1
                        continue
                    written_by_source[source_id] = entry

                if unresolved_written:
                    issues.append(
                        IntakeIssue(
                            severity="warning",
                            code="written_without_source_id",
                            message=f"{unresolved_written} written entries could not be mapped back to source ids",
                        )
                    )
                if duplicate_written:
                    issues.append(
                        IntakeIssue(
                            severity="error",
                            code="written_duplicate_source_id",
                            message=f"{duplicate_written} duplicate source ids found in written file",
                        )
                    )

                written_ids = set(written_by_source)
                summary_existing_count = len(written_ids)
                summary_matched_count = len(source_ids & written_ids)
                summary_missing_count = len(source_ids - written_ids)
                summary_extra_count = len(written_ids - source_ids)
                post_write_verified = True

                if summary_missing_count or summary_extra_count:
                    issues.append(
                        IntakeIssue(
                            severity="error",
                            code="post_write_reconciliation_gap",
                            message=(
                                "written file does not fully reconcile with source snapshot "
                                f"(missing={summary_missing_count}, extra={summary_extra_count})"
                            ),
                        )
                    )
            except Exception as exc:
                issues.append(
                    IntakeIssue(
                        severity="error",
                        code="post_write_verification_failed",
                        message=f"failed to verify written file: {exc}",
                    )
                )
                if write_error is None:
                    write_error = f"post-write verification failed: {exc}"

        report_dir = self.cfg.report_dir
        report_path = report_dir / f"{snapshot.target.venue}-{snapshot.target.year}-{this_run_id}.json"
        unresolved_path: Path | None = None

        non_info_issues = [i for i in issues if i.severity in {"warning", "error"}]
        if non_info_issues:
            unresolved_path = self.cfg.triage_dir / f"{snapshot.target.venue}-{snapshot.target.year}-{this_run_id}.jsonl"
            self._write_jsonl(unresolved_path, [dataclasses.asdict(i) for i in non_info_issues])

        finished = now_iso()
        summary = IntakeSummary(
            target=snapshot.target.target_id,
            adapter=snapshot.adapter,
            file_path=str(file_path),
            source_count=len(source_by_id),
            existing_count=summary_existing_count,
            matched_count=summary_matched_count,
            missing_count=summary_missing_count,
            extra_count=summary_extra_count,
            duplicate_source_count=duplicate_source_count,
            invalid_record_count=invalid_record_count,
            written=wrote,
            report_path=str(report_path),
            unresolved_path=str(unresolved_path) if unresolved_path else None,
            snapshot_path=str(snapshot_path),
            write_error=write_error,
            pre_existing_count=pre_existing_count,
            pre_matched_count=pre_matched_count,
            pre_missing_count=pre_missing_count,
            pre_extra_count=pre_extra_count,
            post_write_verified=post_write_verified,
        )

        report_payload = {
            "run_id": this_run_id,
            "started_at": started,
            "finished_at": finished,
            "target": dataclasses.asdict(snapshot.target),
            "adapter": snapshot.adapter,
            "source_expected_count": snapshot.expected_count,
            "attempts": attempts,
            "summary": dataclasses.asdict(summary),
            "issues": [dataclasses.asdict(i) for i in issues],
            "source_metadata": snapshot.metadata,
            "http_stats": self.http_client.stats(),
        }
        self._write_json(report_path, report_payload)
        return summary, issues

    def run_many(
        self,
        targets: list[tuple[str, int]],
        *,
        write: bool,
        fail_on_gap: bool,
        max_records: int = 0,
        command: str = "run",
    ) -> IntakeRunEnvelope:
        run_id = new_run_id()
        started = now_iso()
        summaries: list[IntakeSummary] = []
        issue_map: dict[str, list[IntakeIssue]] = {}

        for venue, year in targets:
            summary, issues = self.run_target(
                venue=venue,
                year=year,
                write=write,
                fail_on_gap=fail_on_gap,
                max_records=max_records,
                run_id=run_id,
            )
            summaries.append(summary)
            issue_map[f"{venue}:{year}"] = issues

        finished = now_iso()
        return IntakeRunEnvelope(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            command=command,
            config_path=str(self.cfg.config_path),
            summaries=summaries,
            issues=issue_map,
            http_stats=self.http_client.stats(),
        )
