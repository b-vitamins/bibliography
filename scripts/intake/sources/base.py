from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Protocol

from ..models import CatalogSnapshot, IntakeTarget


@dataclasses.dataclass
class CatalogContext:
    target: IntakeTarget
    purpose: str = "plan"
    max_records: int = 0


class CatalogAdapter(Protocol):
    name: str

    def fetch_catalog(self, context: CatalogContext) -> CatalogSnapshot | None:
        ...

    def source_id_from_entry(self, entry: dict[str, Any]) -> str | None:
        ...

    def supports(self, file_path: Path) -> bool:
        ...
