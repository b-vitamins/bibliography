from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .bibtex_io import (
    BibWriteIntegrityError,
    entry_key,
    entry_type,
    get_entry_map,
    parse_bib_file,
    transactional_write_bib_file,
)
from .config import PipelineConfig
from .http_client import CachedHttpClient
from .models import (
    EntryDecision,
    FieldProposal,
    FileRunSummary,
    RunEnvelope,
    SourceRecord,
    WorkItem,
    now_iso,
)
from .normalization import (
    equivalent_text,
    is_prefix_equivalent,
    normalize_text,
    sanitize_bibtex_text,
    word_count,
)
from .sources import build_adapter_registry
from .sources.base import AdapterContext, TransientSourceError


class EnrichmentEngine:
    def __init__(self, cfg: PipelineConfig) -> None:
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
        self.adapters = build_adapter_registry(self.http_client, cfg)

    def close(self) -> None:
        self.http_client.close()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _default_checkpoint_path(self, file_path: Path) -> Path:
        slug = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:10]
        return self.cfg.checkpoint_dir / f"{file_path.stem}-{slug}.json"

    def _load_checkpoint(
        self,
        checkpoint_path: Path,
        file_path: Path,
        file_sha256: str,
    ) -> tuple[set[str], dict[str, dict[str, str]], str | None]:
        if not checkpoint_path.exists():
            return set(), {}, None
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception:
            return set(), {}, None
        if not isinstance(payload, dict):
            return set(), {}, None
        if str(payload.get("file_path", "")) != str(file_path):
            return set(), {}, None
        if str(payload.get("base_file_sha256", "")) != file_sha256:
            return set(), {}, None

        completed_raw = payload.get("completed_success_keys")
        completed = {
            str(item).strip()
            for item in (completed_raw if isinstance(completed_raw, list) else [])
            if str(item).strip()
        }

        applied_raw = payload.get("applied_updates_by_key")
        applied: dict[str, dict[str, str]] = {}
        if isinstance(applied_raw, dict):
            for key, fields in applied_raw.items():
                if not isinstance(key, str) or not key.strip() or not isinstance(fields, dict):
                    continue
                clean_fields: dict[str, str] = {}
                for field, value in fields.items():
                    if not isinstance(field, str):
                        continue
                    clean_fields[field] = str(value)
                if clean_fields:
                    applied[key.strip()] = clean_fields

        last_successful_key = str(payload.get("last_successful_key", "")).strip() or None
        return completed, applied, last_successful_key

    def _flush_checkpoint(
        self,
        checkpoint_path: Path,
        file_path: Path,
        file_sha256: str,
        completed_success_keys: set[str],
        applied_updates_by_key: dict[str, dict[str, str]],
        last_successful_key: str | None,
    ) -> None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "file_path": str(file_path),
            "base_file_sha256": file_sha256,
            "completed_success_keys": sorted(completed_success_keys),
            "applied_updates_by_key": applied_updates_by_key,
            "last_successful_key": last_successful_key,
            "updated_at": now_iso(),
        }
        temp = checkpoint_path.parent / f".{checkpoint_path.name}.tmp-{uuid.uuid4().hex[:8]}"
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(checkpoint_path)

    def _apply_checkpoint_updates(
        self,
        db: Any,
        applied_updates_by_key: dict[str, dict[str, str]],
    ) -> None:
        if not applied_updates_by_key:
            return
        entry_map = get_entry_map(db)
        for key, fields in applied_updates_by_key.items():
            entry = entry_map.get(key)
            if entry is None:
                continue
            for field, value in fields.items():
                entry[field] = value

    def _target_fields(self, entry: dict[str, Any]) -> list[str]:
        etype = entry_type(entry)
        return list(self.cfg.target_fields_by_type.get(etype, []))

    @staticmethod
    def _fields_supported_by_adapter(target_fields: list[str], adapter: object | None) -> list[str]:
        if adapter is None:
            return target_fields
        supported = getattr(adapter, "provided_fields", None)
        if not isinstance(supported, set):
            return target_fields
        return [field for field in target_fields if field in supported]

    def _plan_from_db(
        self,
        file_path: Path,
        db: Any,
        entry_keys: set[str] | None = None,
        max_entries: int = 0,
        overwrite_existing: bool | None = None,
        skip_entry_keys: set[str] | None = None,
    ) -> list[WorkItem]:
        venue = self.cfg.venue_for_file(file_path)
        overwrite = self.cfg.overwrite_existing if overwrite_existing is None else overwrite_existing
        skip_keys = skip_entry_keys or set()

        items: list[WorkItem] = []
        for entry in db.entries:
            key = entry_key(entry)
            if not key or key in skip_keys:
                continue
            if entry_keys and key not in entry_keys:
                continue

            target_fields = self._target_fields(entry)
            if not target_fields:
                continue

            adapter = self._adapter_for_item(file_path, entry, venue.adapter if venue else None)
            if adapter is None:
                continue
            target_fields = self._fields_supported_by_adapter(target_fields, adapter)
            if not target_fields:
                continue

            missing = [field for field in target_fields if not str(entry.get(field, "")).strip()]
            if not missing and not overwrite:
                continue

            items.append(
                WorkItem(
                    file_path=str(file_path),
                    entry_key=key,
                    entry_type=entry_type(entry),
                    target_fields=target_fields,
                    missing_fields=missing,
                    provider=adapter.name if adapter else (venue.adapter if venue else None),
                )
            )
            if max_entries > 0 and len(items) >= max_entries:
                break
        return items

    def plan(
        self,
        file_path: Path,
        entry_keys: set[str] | None = None,
        max_entries: int = 0,
        overwrite_existing: bool | None = None,
    ) -> list[WorkItem]:
        db = parse_bib_file(file_path)
        return self._plan_from_db(
            file_path=file_path,
            db=db,
            entry_keys=entry_keys,
            max_entries=max_entries,
            overwrite_existing=overwrite_existing,
        )

    def _adapter_for_item(self, file_path: Path, entry: dict[str, Any], provider_hint: str | None):
        if provider_hint and provider_hint in self.adapters:
            hinted = self.adapters[provider_hint]
            if hinted.supports(file_path, entry):
                return hinted
        for adapter in self.adapters.values():
            if adapter.supports(file_path, entry):
                return adapter
        return None

    def _domain_allowed(self, value: str, allowed_domains: set[str]) -> bool:
        if not allowed_domains:
            return True
        host = urlparse(value).netloc.lower()
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in allowed_domains)

    @staticmethod
    def _same_host(left: str, right: str) -> bool:
        left_host = urlparse(left).netloc.lower()
        right_host = urlparse(right).netloc.lower()
        return bool(left_host and right_host and left_host == right_host)

    @staticmethod
    def _safe_url_repair(
        entry: dict[str, Any],
        source_fields: dict[str, str],
        current_url: str,
        source_url: str,
    ) -> bool:
        if not current_url or not source_url:
            return False
        if not EnrichmentEngine._same_host(current_url, source_url):
            return False
        entry_title = str(entry.get("title", "")).strip()
        source_title = str(source_fields.get("title", "")).strip()
        if not entry_title or not source_title:
            return False
        return equivalent_text(entry_title, source_title)

    @staticmethod
    def _is_placeholder_author(value: str) -> bool:
        normalized = normalize_text(value)
        if not normalized:
            return False
        if normalized in {"others", "and others", "et al", "et al."}:
            return True
        if " and others" in normalized:
            return True
        if normalized.endswith(" et al") or normalized.endswith(" et al."):
            return True
        return False

    @classmethod
    def _safe_author_repair(cls, current_author: str, source_author: str) -> bool:
        if not current_author or not source_author:
            return False
        if not cls._is_placeholder_author(current_author):
            return False
        return bool(" and " in source_author.lower() or "," in source_author)

    def _build_decision(
        self,
        file_path: Path,
        entry: dict[str, Any],
        item: WorkItem,
        source: SourceRecord,
        overwrite_existing: bool,
        allowed_domains: set[str],
    ) -> EntryDecision:
        proposals: list[FieldProposal] = []
        reasons: list[str] = []
        skipped_fields: list[str] = []

        for field in item.target_fields:
            source_value = sanitize_bibtex_text(str(source.fields.get(field, "")).strip())
            if not source_value:
                skipped_fields.append(field)
                continue

            current_value = str(entry.get(field, "")).strip()

            if field in {"url", "pdf"} and not self._domain_allowed(source_value, allowed_domains):
                reasons.append(f"field {field}: domain outside allowlist")
                skipped_fields.append(field)
                continue

            if field == "abstract":
                if word_count(source_value) < self.cfg.min_abstract_words:
                    reasons.append("field abstract: source abstract too short")
                    skipped_fields.append(field)
                    continue

            if field in self.cfg.protected_fields and current_value:
                equivalent = equivalent_text(current_value, source_value)
                if not equivalent and self.cfg.allow_abstract_prefix_match and field == "abstract":
                    equivalent = is_prefix_equivalent(current_value, source_value)
                if not equivalent and field == "author" and self._is_placeholder_author(current_value):
                    equivalent = True
                if not equivalent:
                    reasons.append(f"field {field}: protected field mismatch")
                    skipped_fields.append(field)
                    continue

            if current_value:
                if equivalent_text(current_value, source_value):
                    skipped_fields.append(field)
                    continue
                if not overwrite_existing and not (
                    field == "url"
                    and self._safe_url_repair(entry, source.fields, current_value, source_value)
                    or (
                        field == "author"
                        and self._safe_author_repair(current_value, source_value)
                    )
                ):
                    skipped_fields.append(field)
                    continue

            proposals.append(
                FieldProposal(
                    field=field,
                    value=source_value,
                    confidence=1.0,
                    reason="canonical_source",
                    evidence=source.evidence_for(field),
                )
            )

        only_short_abstract_rejections = bool(reasons) and all(
            reason == "field abstract: source abstract too short" for reason in reasons
        )

        if proposals:
            status = "planned_update"
        elif only_short_abstract_rejections:
            status = "skipped"
        elif reasons:
            status = "unresolved"
        else:
            status = "skipped"

        return EntryDecision(
            file_path=str(file_path),
            entry_key=item.entry_key,
            status=status,
            adapter=source.adapter,
            applied_fields=[p.field for p in proposals],
            skipped_fields=skipped_fields,
            reasons=reasons,
            proposals=proposals,
        )

    def run_file(
        self,
        file_path: Path,
        entry_keys: set[str] | None = None,
        max_entries: int = 0,
        write: bool = False,
        overwrite_existing: bool | None = None,
        resume: bool = False,
        checkpoint_path: Path | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[FileRunSummary, list[EntryDecision]]:
        run_started_at = now_iso()
        overwrite = self.cfg.overwrite_existing if overwrite_existing is None else overwrite_existing
        db = parse_bib_file(file_path)
        baseline_entries = len(db.entries)
        baseline_comments = len(db.comments)
        file_sha256 = self._file_sha256(file_path) if file_path.exists() else ""

        checkpoint_path_used: Path | None = None
        completed_keys: set[str] = set()
        applied_updates_by_key: dict[str, dict[str, str]] = {}
        last_processed_key: str | None = None
        processed_since_flush = 0

        if resume:
            checkpoint_path_used = checkpoint_path or self._default_checkpoint_path(file_path)
            completed_keys, applied_updates_by_key, last_processed_key = self._load_checkpoint(
                checkpoint_path=checkpoint_path_used,
                file_path=file_path,
                file_sha256=file_sha256,
            )
            self._apply_checkpoint_updates(db, applied_updates_by_key)

        entry_map = get_entry_map(db)
        venue = self.cfg.venue_for_file(file_path)
        allowed_domains = venue.allowed_domains if venue else set()

        work_items = self._plan_from_db(
            file_path=file_path,
            db=db,
            entry_keys=entry_keys,
            max_entries=max_entries,
            overwrite_existing=overwrite,
            skip_entry_keys=completed_keys,
        )

        decisions: list[EntryDecision] = []
        total_items = len(work_items)
        aborted_due_transient_error = False

        def emit_progress(
            item: WorkItem,
            stage: str,
            decision: EntryDecision | None = None,
        ) -> None:
            if progress_callback is None:
                return
            payload: dict[str, Any] = {
                "timestamp": now_iso(),
                "stage": stage,
                "file_path": str(file_path),
                "entry_key": item.entry_key,
                "processed_entries": len(decisions),
                "planned_entries": total_items,
                "provider": item.provider,
            }
            if stage == "start":
                payload["target_fields"] = list(item.target_fields)
                payload["missing_fields"] = list(item.missing_fields)
            if decision is not None:
                payload["status"] = decision.status
                payload["adapter"] = decision.adapter
                payload["applied_fields"] = list(decision.applied_fields)
                payload["skipped_fields"] = list(decision.skipped_fields)
                payload["reason_count"] = len(decision.reasons)
                if decision.reasons:
                    payload["first_reason"] = decision.reasons[0]
            progress_callback(payload)

        def mark_progress_for_checkpoint(
            key: str,
            applied_fields: dict[str, str] | None = None,
        ) -> None:
            nonlocal processed_since_flush, last_processed_key
            if not resume or checkpoint_path_used is None:
                return
            completed_keys.add(key)
            if applied_fields:
                stored = applied_updates_by_key.setdefault(key, {})
                stored.update(applied_fields)
            last_processed_key = key
            processed_since_flush += 1
            if processed_since_flush >= self.cfg.checkpoint_flush_every:
                self._flush_checkpoint(
                    checkpoint_path=checkpoint_path_used,
                    file_path=file_path,
                    file_sha256=file_sha256,
                    completed_success_keys=completed_keys,
                    applied_updates_by_key=applied_updates_by_key,
                    last_successful_key=last_processed_key,
                )
                processed_since_flush = 0

        for item in work_items:
            emit_progress(item, stage="start")
            entry = entry_map.get(item.entry_key)
            if entry is None:
                decision = EntryDecision(
                    file_path=str(file_path),
                    entry_key=item.entry_key,
                    status="error",
                    adapter=None,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=["entry missing during run"],
                    proposals=[],
                )
                decisions.append(decision)
                emit_progress(item, stage="decision", decision=decision)
                mark_progress_for_checkpoint(item.entry_key)
                continue

            adapter = self._adapter_for_item(file_path, entry, item.provider)
            if adapter is None:
                decision = EntryDecision(
                    file_path=str(file_path),
                    entry_key=item.entry_key,
                    status="unresolved",
                    adapter=None,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=["no compatible source adapter"],
                    proposals=[],
                )
                decisions.append(decision)
                emit_progress(item, stage="decision", decision=decision)
                mark_progress_for_checkpoint(item.entry_key)
                continue

            exception_rule = self.cfg.exception_for(file_path, item.entry_key, adapter.name)
            if exception_rule is not None:
                if exception_rule.is_expired():
                    decision = EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="unresolved",
                        adapter=adapter.name,
                        applied_fields=[],
                        skipped_fields=item.target_fields,
                        reasons=[
                            f"exception rule expired: {exception_rule.reason_code}",
                        ],
                        proposals=[],
                    )
                    decisions.append(decision)
                    emit_progress(item, stage="decision", decision=decision)
                    mark_progress_for_checkpoint(item.entry_key)
                    continue
                if exception_rule.action == "skip":
                    reason_parts = [
                        f"exception ledger skip: {exception_rule.reason_code}",
                        f"evidence: {exception_rule.evidence}",
                    ]
                    if exception_rule.review_after:
                        reason_parts.append(f"review_after: {exception_rule.review_after.isoformat()}")
                    if exception_rule.note:
                        reason_parts.append(f"note: {exception_rule.note}")
                    decision = EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="skipped",
                        adapter=adapter.name,
                        applied_fields=[],
                        skipped_fields=item.target_fields,
                        reasons=reason_parts,
                        proposals=[],
                    )
                    decisions.append(decision)
                    emit_progress(item, stage="decision", decision=decision)
                    mark_progress_for_checkpoint(item.entry_key)
                    continue

            try:
                source = adapter.fetch(
                    AdapterContext(file_path=file_path, entry_key=item.entry_key, entry=entry)
                )
            except TransientSourceError as exc:
                decision = EntryDecision(
                    file_path=str(file_path),
                    entry_key=item.entry_key,
                    status="error",
                    adapter=exc.adapter or adapter.name,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=[f"transient source error: {exc.message}"],
                    proposals=[],
                )
                decisions.append(decision)
                emit_progress(item, stage="decision", decision=decision)
                aborted_due_transient_error = True
                break
            except Exception as exc:
                decision = EntryDecision(
                    file_path=str(file_path),
                    entry_key=item.entry_key,
                    status="error",
                    adapter=adapter.name,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=[f"source adapter exception: {exc}"],
                    proposals=[],
                )
                decisions.append(decision)
                emit_progress(item, stage="decision", decision=decision)
                mark_progress_for_checkpoint(item.entry_key)
                continue
            if source is None:
                raw_url = str(entry.get("url", "")).strip()
                raw_pdf = str(entry.get("pdf", "")).strip()
                if adapter.name == "pmlr" and not raw_url and not raw_pdf:
                    decision = EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="skipped",
                        adapter=adapter.name,
                        applied_fields=[],
                        skipped_fields=item.target_fields,
                        reasons=["no source locator present"],
                        proposals=[],
                    )
                    decisions.append(decision)
                    emit_progress(item, stage="decision", decision=decision)
                    mark_progress_for_checkpoint(item.entry_key)
                    continue
                decision = EntryDecision(
                    file_path=str(file_path),
                    entry_key=item.entry_key,
                    status="unresolved",
                    adapter=adapter.name,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=["no source record returned"],
                    proposals=[],
                )
                decisions.append(decision)
                emit_progress(item, stage="decision", decision=decision)
                mark_progress_for_checkpoint(item.entry_key)
                continue

            decision = self._build_decision(
                file_path=file_path,
                entry=entry,
                item=item,
                source=source,
                overwrite_existing=overwrite,
                allowed_domains=allowed_domains,
            )

            if write and decision.status == "planned_update":
                applied_fields: dict[str, str] = {}
                for proposal in decision.proposals:
                    entry[proposal.field] = proposal.value
                    applied_fields[proposal.field] = proposal.value
                mark_progress_for_checkpoint(item.entry_key, applied_fields=applied_fields)
            else:
                mark_progress_for_checkpoint(item.entry_key)

            decisions.append(decision)
            emit_progress(item, stage="decision", decision=decision)

        if aborted_due_transient_error:
            remaining = max(0, total_items - len(decisions))
            decisions.append(
                EntryDecision(
                    file_path=str(file_path),
                    entry_key="__run__",
                    status="error",
                    adapter=None,
                    applied_fields=[],
                    skipped_fields=[],
                    reasons=[
                        f"run aborted after transient source error; remaining_entries={remaining}"
                    ],
                    proposals=[],
                )
            )

        if resume and checkpoint_path_used is not None and processed_since_flush > 0:
            self._flush_checkpoint(
                checkpoint_path=checkpoint_path_used,
                file_path=file_path,
                file_sha256=file_sha256,
                completed_success_keys=completed_keys,
                applied_updates_by_key=applied_updates_by_key,
                last_successful_key=last_processed_key,
            )
            processed_since_flush = 0

        wrote = False
        write_error: str | None = None
        planned_update_keys = {
            d.entry_key for d in decisions if d.status == "planned_update"
        }
        replay_only_keys = set(applied_updates_by_key.keys()) - planned_update_keys
        has_checkpoint_replay = bool(resume and checkpoint_path_used and applied_updates_by_key)

        if write and (planned_update_keys or has_checkpoint_replay):
            try:
                transactional_write_bib_file(
                    path=file_path,
                    db=db,
                    baseline_entries=baseline_entries,
                    baseline_comments=baseline_comments,
                    max_comment_increase=0,
                    rollback_dir=self.cfg.report_dir / "write-failures",
                )
                wrote = True
                for decision in decisions:
                    if decision.status == "planned_update":
                        decision.status = "updated"
                for key in sorted(replay_only_keys):
                    fields = sorted((applied_updates_by_key.get(key) or {}).keys())
                    if not fields:
                        continue
                    decisions.append(
                        EntryDecision(
                            file_path=str(file_path),
                            entry_key=key,
                            status="updated",
                            adapter=None,
                            applied_fields=fields,
                            skipped_fields=[],
                            reasons=["checkpoint replayed pending in-memory updates"],
                            proposals=[],
                        )
                    )
            except BibWriteIntegrityError as exc:
                write_error = str(exc)
                decisions.append(
                    EntryDecision(
                        file_path=str(file_path),
                        entry_key="__write_transaction__",
                        status="error",
                        adapter=None,
                        applied_fields=[],
                        skipped_fields=[],
                        reasons=[f"transactional write failed: {exc}"],
                        proposals=[],
                    )
                )

        self.cfg.report_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.triage_dir.mkdir(parents=True, exist_ok=True)

        stem = file_path.stem
        run_id = uuid.uuid4().hex[:10]
        report_path = self.cfg.report_dir / f"{stem}-{run_id}.json"
        unresolved_path: Path | None = None

        unresolved = [d for d in decisions if d.status in {"unresolved", "error"}]
        if unresolved:
            unresolved_path = self.cfg.triage_dir / f"{stem}-{run_id}.jsonl"
            with unresolved_path.open("w", encoding="utf-8") as f:
                for decision in unresolved:
                    f.write(json.dumps(dataclasses.asdict(decision), sort_keys=True) + "\n")

        summary = FileRunSummary(
            file_path=str(file_path),
            planned_entries=len(work_items),
            proposed_entries=sum(1 for d in decisions if d.proposals),
            updated_entries=sum(1 for d in decisions if d.status == "updated"),
            unresolved_entries=sum(1 for d in decisions if d.status == "unresolved"),
            skipped_entries=sum(1 for d in decisions if d.status == "skipped"),
            error_entries=sum(1 for d in decisions if d.status == "error"),
            written=wrote,
            report_path=str(report_path),
            unresolved_path=str(unresolved_path) if unresolved_path else None,
            checkpoint_path=str(checkpoint_path_used) if checkpoint_path_used else None,
            write_error=write_error,
        )

        envelope = RunEnvelope(
            run_id=run_id,
            started_at=run_started_at,
            finished_at=now_iso(),
            command="run_file",
            config_path=str(self.cfg.config_path),
            files=[summary],
            decisions=decisions,
            http_stats=self.http_client.stats(),
        )
        report_path.write_text(json.dumps(envelope.to_json(), indent=2, sort_keys=True), encoding="utf-8")

        if resume and checkpoint_path_used is not None:
            if write_error is None:
                checkpoint_path_used.unlink(missing_ok=True)
            else:
                self._flush_checkpoint(
                    checkpoint_path=checkpoint_path_used,
                    file_path=file_path,
                    file_sha256=file_sha256,
                    completed_success_keys=completed_keys,
                    applied_updates_by_key=applied_updates_by_key,
                    last_successful_key=last_processed_key,
                )

        return summary, decisions
