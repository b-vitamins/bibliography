"""Shared locations for transient bibops runtime artifacts."""

from __future__ import annotations

import os
from pathlib import Path

RUNTIME_DIR_ENV = "BIBOPS_RUNTIME_DIR"


def bibops_runtime_dir() -> Path:
    value = os.environ.get(RUNTIME_DIR_ENV, "").strip()
    if value:
        return Path(value)
    return Path("tmp/bibops")


def bibops_runtime_path(*parts: str) -> Path:
    return bibops_runtime_dir().joinpath(*parts)
