from __future__ import annotations

import dataclasses
from typing import Any

from core.time_utils import now_iso


@dataclasses.dataclass
class IntakeTarget:
    venue: str
    year: int
    file_path: str
    adapter: str
    params: dict[str, Any]

    @property
    def target_id(self) -> str:
        return f"{self.venue}:{self.year}"


@dataclasses.dataclass
class IntakeRecord:
    source_id: str
    source_url: str
    title: str
    authors: list[str]
    year: int
    booktitle: str
    publisher: str | None = None
    url: str | None = None
    pdf: str | None = None
    abstract: str | None = None
    doi: str | None = None
    note: str | None = None
    extra_fields: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CatalogSnapshot:
    adapter: str
    target: IntakeTarget
    fetched_at: str
    records: list[IntakeRecord]
    expected_count: int | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class IntakeIssue:
    severity: str
    code: str
    message: str
    source_id: str | None = None
    entry_key: str | None = None
    details: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class IntakeSummary:
    target: str
    adapter: str
    file_path: str
    source_count: int
    existing_count: int
    matched_count: int
    missing_count: int
    extra_count: int
    duplicate_source_count: int
    invalid_record_count: int
    written: bool
    report_path: str
    unresolved_path: str | None
    snapshot_path: str | None
    write_error: str | None = None
    pre_existing_count: int | None = None
    pre_matched_count: int | None = None
    pre_missing_count: int | None = None
    pre_extra_count: int | None = None
    post_write_verified: bool = False


@dataclasses.dataclass
class IntakeRunEnvelope:
    run_id: str
    started_at: str
    finished_at: str
    command: str
    config_path: str
    summaries: list[IntakeSummary]
    issues: dict[str, list[IntakeIssue]]
    http_stats: dict[str, int | float] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "command": self.command,
            "config_path": self.config_path,
            "summaries": [dataclasses.asdict(summary) for summary in self.summaries],
            "issues": {
                target: [dataclasses.asdict(issue) for issue in issues]
                for target, issues in self.issues.items()
            },
            "http_stats": dict(self.http_stats or {}),
        }


def new_run_id() -> str:
    stamp = now_iso().replace("-", "").replace(":", "")
    return f"intake-{stamp[:15]}"
