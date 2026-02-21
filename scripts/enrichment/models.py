from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from typing import Any


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def text_sha256(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


@dataclasses.dataclass
class WorkItem:
    file_path: str
    entry_key: str
    entry_type: str
    target_fields: list[str]
    missing_fields: list[str]
    provider: str | None


@dataclasses.dataclass
class SourceEvidence:
    adapter: str
    source_url: str
    fetched_at: str
    value_sha256: str


@dataclasses.dataclass
class SourceRecord:
    adapter: str
    source_url: str
    fetched_at: str
    fields: dict[str, str]

    def evidence_for(self, field: str) -> SourceEvidence:
        return SourceEvidence(
            adapter=self.adapter,
            source_url=self.source_url,
            fetched_at=self.fetched_at,
            value_sha256=text_sha256(self.fields.get(field, "")),
        )


@dataclasses.dataclass
class FieldProposal:
    field: str
    value: str
    confidence: float
    reason: str
    evidence: SourceEvidence


@dataclasses.dataclass
class EntryDecision:
    file_path: str
    entry_key: str
    status: str
    adapter: str | None
    applied_fields: list[str]
    skipped_fields: list[str]
    reasons: list[str]
    proposals: list[FieldProposal]


@dataclasses.dataclass
class FileRunSummary:
    file_path: str
    planned_entries: int
    proposed_entries: int
    updated_entries: int
    unresolved_entries: int
    skipped_entries: int
    error_entries: int
    written: bool
    report_path: str
    unresolved_path: str | None


@dataclasses.dataclass
class RunEnvelope:
    run_id: str
    started_at: str
    finished_at: str
    command: str
    config_path: str
    files: list[FileRunSummary]
    decisions: list[EntryDecision]

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "command": self.command,
            "config_path": self.config_path,
            "files": [dataclasses.asdict(f) for f in self.files],
            "decisions": [dataclasses.asdict(d) for d in self.decisions],
        }
