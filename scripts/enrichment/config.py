from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("ops/enrichment-pipeline.toml")


@dataclasses.dataclass
class VenuePolicy:
    name: str
    path_contains: str
    adapter: str
    allowed_domains: set[str]

    def matches(self, file_path: Path) -> bool:
        return self.path_contains in str(file_path)


@dataclasses.dataclass
class PipelineConfig:
    config_path: Path
    target_fields_by_type: dict[str, list[str]]
    protected_fields: set[str]
    overwrite_existing: bool
    min_abstract_words: int
    allow_abstract_prefix_match: bool
    report_dir: Path
    triage_dir: Path
    source_cache_path: Path
    timeout_seconds: float
    max_retries: int
    max_validation_retries: int
    host_min_interval_seconds: float
    backoff_base_seconds: float
    backoff_max_seconds: float
    user_agent: str
    venues: list[VenuePolicy]

    def venue_for_file(self, file_path: Path) -> VenuePolicy | None:
        for venue in self.venues:
            if venue.matches(file_path):
                return venue
        return None


def _default_config(path: Path) -> PipelineConfig:
    return PipelineConfig(
        config_path=path,
        target_fields_by_type={"inproceedings": ["url", "pdf", "abstract", "doi"]},
        protected_fields={"author", "title", "booktitle", "year"},
        overwrite_existing=False,
        min_abstract_words=25,
        allow_abstract_prefix_match=False,
        report_dir=Path("ops/enrichment-runs"),
        triage_dir=Path("ops/unresolved/enrichment"),
        source_cache_path=Path("ops/enrichment-source-cache.json"),
        timeout_seconds=20.0,
        max_retries=2,
        max_validation_retries=4,
        host_min_interval_seconds=1.0,
        backoff_base_seconds=1.0,
        backoff_max_seconds=30.0,
        user_agent="bibliography-enrichment-pipeline/1.0",
        venues=[
            VenuePolicy(
                name="iclr",
                path_contains="conferences/iclr/",
                adapter="openreview",
                allowed_domains={"openreview.net"},
            ),
            VenuePolicy(
                name="neurips",
                path_contains="conferences/neurips/",
                adapter="neurips_proceedings",
                allowed_domains={
                    "proceedings.neurips.cc",
                    "neurips.cc",
                    "papers.nips.cc",
                },
            ),
        ],
    )


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def load_pipeline_config(path: Path | None = None) -> PipelineConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    cfg = _default_config(config_path)

    if not config_path.exists():
        return cfg

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    defaults = data.get("defaults")
    if isinstance(defaults, dict):
        if isinstance(defaults.get("overwrite_existing"), bool):
            cfg.overwrite_existing = defaults["overwrite_existing"]
        if isinstance(defaults.get("min_abstract_words"), int) and defaults["min_abstract_words"] > 0:
            cfg.min_abstract_words = defaults["min_abstract_words"]
        if isinstance(defaults.get("allow_abstract_prefix_match"), bool):
            cfg.allow_abstract_prefix_match = defaults["allow_abstract_prefix_match"]
        if isinstance(defaults.get("report_dir"), str) and defaults["report_dir"].strip():
            cfg.report_dir = Path(defaults["report_dir"].strip())
        if isinstance(defaults.get("triage_dir"), str) and defaults["triage_dir"].strip():
            cfg.triage_dir = Path(defaults["triage_dir"].strip())
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
        if isinstance(defaults.get("backoff_base_seconds"), (int, float)):
            cfg.backoff_base_seconds = max(0.1, float(defaults["backoff_base_seconds"]))
        if isinstance(defaults.get("backoff_max_seconds"), (int, float)):
            cfg.backoff_max_seconds = max(cfg.backoff_base_seconds, float(defaults["backoff_max_seconds"]))
        if isinstance(defaults.get("user_agent"), str) and defaults["user_agent"].strip():
            cfg.user_agent = defaults["user_agent"].strip()

    targets = data.get("targets")
    if isinstance(targets, dict):
        parsed_targets: dict[str, list[str]] = {}
        for entry_type, value in targets.items():
            if isinstance(entry_type, str):
                fields = _as_str_list(value)
                if fields:
                    parsed_targets[entry_type.lower()] = fields
        if parsed_targets:
            cfg.target_fields_by_type = parsed_targets

    policy = data.get("policy")
    if isinstance(policy, dict):
        protected = _as_str_list(policy.get("protected_fields"))
        if protected:
            cfg.protected_fields = {x.lower() for x in protected}

    venues = data.get("venues")
    if isinstance(venues, list):
        parsed_venues: list[VenuePolicy] = []
        for raw in venues:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            path_contains = raw.get("path_contains")
            adapter = raw.get("adapter")
            allowed_domains = _as_str_list(raw.get("allowed_domains"))
            if not all(isinstance(x, str) and x.strip() for x in [name, path_contains, adapter]):
                continue
            parsed_venues.append(
                VenuePolicy(
                    name=name.strip(),
                    path_contains=path_contains.strip(),
                    adapter=adapter.strip(),
                    allowed_domains={d.strip().lower() for d in allowed_domains if d.strip()},
                )
            )
        if parsed_venues:
            cfg.venues = parsed_venues

    return cfg
