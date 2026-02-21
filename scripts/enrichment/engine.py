from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .bibtex_io import entry_key, entry_type, get_entry_map, parse_bib_file, write_bib_file
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
from .normalization import equivalent_text, is_prefix_equivalent, word_count
from .sources import build_adapter_registry
from .sources.base import AdapterContext


class EnrichmentEngine:
    def __init__(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self.http_client = CachedHttpClient(
            timeout_seconds=cfg.timeout_seconds,
            max_retries=cfg.max_retries,
            user_agent=cfg.user_agent,
            cache_path=cfg.source_cache_path,
        )
        self.adapters = build_adapter_registry(self.http_client)

    def close(self) -> None:
        self.http_client.close()

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

    def plan(
        self,
        file_path: Path,
        entry_keys: set[str] | None = None,
        max_entries: int = 0,
        overwrite_existing: bool | None = None,
    ) -> list[WorkItem]:
        db = parse_bib_file(file_path)
        venue = self.cfg.venue_for_file(file_path)
        overwrite = self.cfg.overwrite_existing if overwrite_existing is None else overwrite_existing

        items: list[WorkItem] = []
        for entry in db.entries:
            key = entry_key(entry)
            if not key:
                continue
            if entry_keys and key not in entry_keys:
                continue

            target_fields = self._target_fields(entry)
            if not target_fields:
                continue

            adapter = self._adapter_for_item(file_path, entry, venue.adapter if venue else None)
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
            source_value = str(source.fields.get(field, "")).strip()
            if not source_value:
                skipped_fields.append(field)
                continue

            current_value = str(entry.get(field, "")).strip()

            if field in {"url", "pdf"} and not self._domain_allowed(source_value, allowed_domains):
                reasons.append(f"field {field}: domain outside allowlist")
                continue

            if field == "abstract":
                if word_count(source_value) < self.cfg.min_abstract_words:
                    reasons.append("field abstract: source abstract too short")
                    continue

            if field in self.cfg.protected_fields and current_value:
                equivalent = equivalent_text(current_value, source_value)
                if not equivalent and self.cfg.allow_abstract_prefix_match and field == "abstract":
                    equivalent = is_prefix_equivalent(current_value, source_value)
                if not equivalent:
                    reasons.append(f"field {field}: protected field mismatch")
                    continue

            if current_value:
                if equivalent_text(current_value, source_value):
                    skipped_fields.append(field)
                    continue
                if not overwrite_existing:
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

        if reasons:
            status = "unresolved"
        elif proposals:
            status = "planned_update"
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
    ) -> tuple[FileRunSummary, list[EntryDecision]]:
        run_started_at = now_iso()
        overwrite = self.cfg.overwrite_existing if overwrite_existing is None else overwrite_existing
        db = parse_bib_file(file_path)
        entry_map = get_entry_map(db)
        venue = self.cfg.venue_for_file(file_path)
        allowed_domains = venue.allowed_domains if venue else set()

        work_items = self.plan(
            file_path=file_path,
            entry_keys=entry_keys,
            max_entries=max_entries,
            overwrite_existing=overwrite,
        )

        decisions: list[EntryDecision] = []

        for item in work_items:
            entry = entry_map.get(item.entry_key)
            if entry is None:
                decisions.append(
                    EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="error",
                        adapter=None,
                        applied_fields=[],
                        skipped_fields=[],
                        reasons=["entry missing during run"],
                        proposals=[],
                    )
                )
                continue

            adapter = self._adapter_for_item(file_path, entry, item.provider)
            if adapter is None:
                decisions.append(
                    EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="unresolved",
                        adapter=None,
                        applied_fields=[],
                        skipped_fields=[],
                        reasons=["no compatible source adapter"],
                        proposals=[],
                    )
                )
                continue

            source = adapter.fetch(
                AdapterContext(file_path=file_path, entry_key=item.entry_key, entry=entry)
            )
            if source is None:
                decisions.append(
                    EntryDecision(
                        file_path=str(file_path),
                        entry_key=item.entry_key,
                        status="unresolved",
                        adapter=adapter.name,
                        applied_fields=[],
                        skipped_fields=[],
                        reasons=["no source record returned"],
                        proposals=[],
                    )
                )
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
                for proposal in decision.proposals:
                    entry[proposal.field] = proposal.value
                decision.status = "updated"

            decisions.append(decision)

        wrote = False
        if write and any(d.status == "updated" for d in decisions):
            write_bib_file(file_path, db)
            wrote = True

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
            proposed_entries=sum(1 for d in decisions if d.status == "planned_update"),
            updated_entries=sum(1 for d in decisions if d.status == "updated"),
            unresolved_entries=sum(1 for d in decisions if d.status == "unresolved"),
            skipped_entries=sum(1 for d in decisions if d.status == "skipped"),
            error_entries=sum(1 for d in decisions if d.status == "error"),
            written=wrote,
            report_path=str(report_path),
            unresolved_path=str(unresolved_path) if unresolved_path else None,
        )

        envelope = RunEnvelope(
            run_id=run_id,
            started_at=run_started_at,
            finished_at=now_iso(),
            command="run_file",
            config_path=str(self.cfg.config_path),
            files=[summary],
            decisions=decisions,
        )
        report_path.write_text(json.dumps(envelope.to_json(), indent=2, sort_keys=True), encoding="utf-8")

        return summary, decisions
