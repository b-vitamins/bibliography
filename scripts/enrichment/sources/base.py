from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Protocol

from ..models import SourceRecord


@dataclasses.dataclass
class AdapterContext:
    file_path: Path
    entry_key: str
    entry: dict[str, Any]


class TransientSourceError(RuntimeError):
    """Retryable source error (rate limiting, transient upstream failure)."""

    def __init__(self, adapter: str, message: str) -> None:
        super().__init__(message)
        self.adapter = adapter
        self.message = message


class SourceAdapter(Protocol):
    name: str

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        ...

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        ...
