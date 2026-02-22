from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path
from typing import Any

from .models import IntakeTarget

DEFAULT_CONFIG_PATH = Path("ops/intake-pipeline.toml")


@dataclasses.dataclass
class AdapterBinding:
    name: str
    params: dict[str, Any]


@dataclasses.dataclass
class VenuePolicy:
    name: str
    file_path_template: str
    adapters: list[AdapterBinding]
    default_booktitle: str | None = None
    default_publisher: str | None = None

    def target_for_year(self, year: int) -> IntakeTarget:
        merged = dict(self.adapters[0].params)
        if self.default_booktitle and "booktitle" not in merged:
            merged["booktitle"] = self.default_booktitle
        if self.default_publisher and "publisher" not in merged:
            merged["publisher"] = self.default_publisher
        return IntakeTarget(
            venue=self.name,
            year=year,
            file_path=self.file_path_template.format(year=year, venue=self.name),
            adapter=self.adapters[0].name,
            params=merged,
        )


@dataclasses.dataclass
class IntakeConfig:
    config_path: Path
    report_dir: Path
    triage_dir: Path
    snapshot_dir: Path
    global_key_globs: list[str]
    source_cache_path: Path
    timeout_seconds: float
    max_retries: int
    max_validation_retries: int
    host_min_interval_seconds: float
    host_min_interval_by_host: dict[str, float]
    host_circuit_breaker_threshold: int
    host_circuit_breaker_cooldown_seconds: float
    backoff_base_seconds: float
    backoff_max_seconds: float
    user_agent: str
    venues: dict[str, VenuePolicy]

    def venue(self, name: str) -> VenuePolicy | None:
        return self.venues.get(name.strip().lower())

    def build_target(self, venue: str, year: int) -> IntakeTarget:
        policy = self.venue(venue)
        if policy is None:
            raise KeyError(f"unknown venue `{venue}`")
        target = policy.target_for_year(year)
        target.venue = policy.name
        return target


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _as_float_dict(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(raw, (int, float)):
            continue
        out[key.strip().lower()] = max(0.0, float(raw))
    return out


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _default_config(path: Path) -> IntakeConfig:
    venues = {
        "iclr": VenuePolicy(
            name="iclr",
            file_path_template="conferences/iclr/{year}.bib",
            adapters=[
                AdapterBinding(
                    name="openreview_conference",
                    params={
                        "conference_prefix": "ICLR.cc",
                        "conference_track": "Conference",
                        "booktitle": "ICLR",
                        "publisher": "OpenReview.net",
                        "require_venue": True,
                    },
                )
            ],
            default_booktitle="ICLR",
            default_publisher="OpenReview.net",
        ),
        "neurips": VenuePolicy(
            name="neurips",
            file_path_template="conferences/neurips/{year}.bib",
            adapters=[
                AdapterBinding(
                    name="neurips_proceedings_catalog",
                    params={
                        "booktitle": "Advances in Neural Information Processing Systems",
                        "publisher": "Curran Associates, Inc.",
                    },
                )
            ],
            default_booktitle="Advances in Neural Information Processing Systems",
            default_publisher="Curran Associates, Inc.",
        ),
        "icml": VenuePolicy(
            name="icml",
            file_path_template="conferences/icml/{year}.bib",
            adapters=[
                AdapterBinding(
                    name="openreview_conference",
                    params={
                        "conference_prefix": "ICML.cc",
                        "conference_track": "Conference",
                        "booktitle": "ICML",
                        "publisher": "OpenReview.net",
                        "require_venue": True,
                    },
                )
            ],
            default_booktitle="ICML",
            default_publisher="OpenReview.net",
        ),
    }
    return IntakeConfig(
        config_path=path,
        report_dir=Path("ops/intake-runs"),
        triage_dir=Path("ops/unresolved/intake"),
        snapshot_dir=Path("ops/intake-snapshots"),
        global_key_globs=[
            "books/**/*.bib",
            "conferences/**/*.bib",
            "collections/**/*.bib",
            "references/**/*.bib",
            "courses/**/*.bib",
            "theses/**/*.bib",
            "presentations/**/*.bib",
        ],
        source_cache_path=Path("ops/intake-source-cache.json"),
        timeout_seconds=20.0,
        max_retries=2,
        max_validation_retries=4,
        host_min_interval_seconds=1.0,
        host_min_interval_by_host={
            "openreview.net": 0.5,
            "api.openreview.net": 1.1,
            "api2.openreview.net": 1.1,
            "proceedings.neurips.cc": 0.2,
            "proceedings.mlr.press": 0.2,
        },
        host_circuit_breaker_threshold=0,
        host_circuit_breaker_cooldown_seconds=0.0,
        backoff_base_seconds=1.0,
        backoff_max_seconds=30.0,
        user_agent="bibliography-intake-pipeline/1.0",
        venues=venues,
    )


def load_intake_config(path: Path | None = None) -> IntakeConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    cfg = _default_config(config_path)
    if not config_path.exists():
        return cfg

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    defaults = data.get("defaults")
    if isinstance(defaults, dict):
        if isinstance(defaults.get("report_dir"), str) and defaults["report_dir"].strip():
            cfg.report_dir = Path(defaults["report_dir"].strip())
        if isinstance(defaults.get("triage_dir"), str) and defaults["triage_dir"].strip():
            cfg.triage_dir = Path(defaults["triage_dir"].strip())
        if isinstance(defaults.get("snapshot_dir"), str) and defaults["snapshot_dir"].strip():
            cfg.snapshot_dir = Path(defaults["snapshot_dir"].strip())
        global_key_globs = _as_str_list(defaults.get("global_key_globs"))
        if global_key_globs:
            cfg.global_key_globs = global_key_globs
        if isinstance(defaults.get("source_cache_path"), str) and defaults["source_cache_path"].strip():
            cfg.source_cache_path = Path(defaults["source_cache_path"].strip())
        if isinstance(defaults.get("timeout_seconds"), (int, float)):
            cfg.timeout_seconds = float(defaults["timeout_seconds"])
        if isinstance(defaults.get("max_retries"), int) and defaults["max_retries"] >= 0:
            cfg.max_retries = defaults["max_retries"]
        if isinstance(defaults.get("max_validation_retries"), int) and defaults["max_validation_retries"] >= 0:
            cfg.max_validation_retries = defaults["max_validation_retries"]
        if isinstance(defaults.get("host_min_interval_seconds"), (int, float)):
            cfg.host_min_interval_seconds = max(0.0, float(defaults["host_min_interval_seconds"]))
        host_intervals = _as_float_dict(defaults.get("host_min_interval_by_host"))
        if host_intervals:
            cfg.host_min_interval_by_host = host_intervals
        if isinstance(defaults.get("host_circuit_breaker_threshold"), int):
            cfg.host_circuit_breaker_threshold = max(0, defaults["host_circuit_breaker_threshold"])
        if isinstance(defaults.get("host_circuit_breaker_cooldown_seconds"), (int, float)):
            cfg.host_circuit_breaker_cooldown_seconds = max(0.0, float(defaults["host_circuit_breaker_cooldown_seconds"]))
        if isinstance(defaults.get("backoff_base_seconds"), (int, float)):
            cfg.backoff_base_seconds = max(0.1, float(defaults["backoff_base_seconds"]))
        if isinstance(defaults.get("backoff_max_seconds"), (int, float)):
            cfg.backoff_max_seconds = max(cfg.backoff_base_seconds, float(defaults["backoff_max_seconds"]))
        if isinstance(defaults.get("user_agent"), str) and defaults["user_agent"].strip():
            cfg.user_agent = defaults["user_agent"].strip()

    venues_raw = data.get("venues")
    if isinstance(venues_raw, list):
        parsed: dict[str, VenuePolicy] = {}
        for raw in venues_raw:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip().lower()
            if not name:
                continue
            template = str(raw.get("file_path_template", "")).strip()
            if not template:
                template = f"conferences/{name}" + "/{year}.bib"
            default_booktitle = str(raw.get("default_booktitle", "")).strip() or None
            default_publisher = str(raw.get("default_publisher", "")).strip() or None

            adapters: list[AdapterBinding] = []
            adapter_rows = raw.get("adapters")
            if isinstance(adapter_rows, list):
                for adapter_row in adapter_rows:
                    if not isinstance(adapter_row, dict):
                        continue
                    adapter_name = str(adapter_row.get("name", "")).strip()
                    if not adapter_name:
                        continue
                    adapters.append(
                        AdapterBinding(
                            name=adapter_name,
                            params=_as_dict(adapter_row.get("params")),
                        )
                    )
            if not adapters:
                adapter_name = str(raw.get("adapter", "")).strip()
                if adapter_name:
                    adapters.append(
                        AdapterBinding(
                            name=adapter_name,
                            params=_as_dict(raw.get("params")),
                        )
                    )
            if not adapters:
                continue
            parsed[name] = VenuePolicy(
                name=name,
                file_path_template=template,
                adapters=adapters,
                default_booktitle=default_booktitle,
                default_publisher=default_publisher,
            )
        if parsed:
            cfg.venues = parsed

    return cfg


def parse_target_tokens(tokens: list[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for token in tokens:
        raw = token.strip()
        if not raw or ":" not in raw:
            raise ValueError(f"invalid target `{token}`; expected venue:year")
        venue, year_raw = raw.split(":", 1)
        venue = venue.strip().lower()
        year_raw = year_raw.strip()
        if not venue or not year_raw.isdigit():
            raise ValueError(f"invalid target `{token}`; expected venue:year")
        year = int(year_raw)
        if year < 1900 or year > 2100:
            raise ValueError(f"target year out of bounds in `{token}`")
        out.append((venue, year))
    return out
