from __future__ import annotations

import dataclasses
import datetime as dt
import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("ops/enrichment-pipeline.toml")
DEFAULT_EXCEPTIONS_PATH = Path("ops/enrichment-exceptions.toml")
DEFAULT_DOTENV_PATH = Path(".env")
_DOTENV_CACHE: dict[str, str] | None = None


@dataclasses.dataclass
class VenuePolicy:
    name: str
    path_contains: str
    adapter: str
    allowed_domains: set[str]

    def matches(self, file_path: Path) -> bool:
        # Allow explicit "match all files" venue policies for mode-specific configs.
        if self.path_contains in {"", "*"}:
            return True
        return self.path_contains in str(file_path)


@dataclasses.dataclass
class ExceptionRule:
    entry_key: str
    action: str
    reason_code: str
    evidence: str
    review_after: dt.date | None = None
    file_path_contains: str | None = None
    adapter: str | None = None
    note: str | None = None

    def matches(self, file_path: Path, entry_key: str, adapter: str | None) -> bool:
        if self.entry_key != entry_key:
            return False
        if self.file_path_contains and self.file_path_contains not in str(file_path):
            return False
        if self.adapter and (adapter or "") != self.adapter:
            return False
        return True

    def is_expired(self) -> bool:
        return bool(self.review_after and dt.date.today() > self.review_after)


@dataclasses.dataclass
class PipelineConfig:
    config_path: Path
    exceptions_path: Path
    target_fields_by_type: dict[str, list[str]]
    protected_fields: set[str]
    overwrite_existing: bool
    min_abstract_words: int
    allow_abstract_prefix_match: bool
    report_dir: Path
    triage_dir: Path
    source_cache_path: Path
    openalex_mailto: str
    openalex_api_key: str
    semantic_scholar_api_key: str
    semantic_scholar_min_title_score: float
    semantic_scholar_min_confidence: float
    arxiv_min_title_score: float
    arxiv_min_confidence: float
    arxiv_enable_openalex: bool
    arxiv_openalex_max_results: int
    arxiv_max_results: int
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
    checkpoint_dir: Path
    checkpoint_flush_every: int
    venues: list[VenuePolicy]
    exceptions: list[ExceptionRule]

    def venue_for_file(self, file_path: Path) -> VenuePolicy | None:
        for venue in self.venues:
            if venue.matches(file_path):
                return venue
        return None

    def exception_for(self, file_path: Path, entry_key: str, adapter: str | None) -> ExceptionRule | None:
        for rule in self.exceptions:
            if rule.matches(file_path, entry_key, adapter):
                return rule
        return None


def _parse_date(value: object) -> dt.date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except Exception:
        return None


def _load_dotenv(path: Path = DEFAULT_DOTENV_PATH) -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE
    values: dict[str, str] = {}
    if not path.exists():
        _DOTENV_CACHE = values
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        _DOTENV_CACHE = values
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    _DOTENV_CACHE = values
    return values


def _env_or_dotenv(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value is not None and value != "":
        return value
    return _load_dotenv().get(key, default)


def _load_exception_rules(path: Path) -> list[ExceptionRule]:
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("exceptions")
    if not isinstance(rows, list):
        return []

    out: list[ExceptionRule] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        entry_key = raw.get("entry_key")
        action = raw.get("action")
        reason_code = raw.get("reason_code")
        evidence = raw.get("evidence")
        if not all(isinstance(x, str) and x.strip() for x in [entry_key, action, reason_code, evidence]):
            continue

        rule = ExceptionRule(
            entry_key=entry_key.strip(),
            action=action.strip().lower(),
            reason_code=reason_code.strip(),
            evidence=evidence.strip(),
            review_after=_parse_date(raw.get("review_after")),
            file_path_contains=raw.get("file_path_contains").strip() if isinstance(raw.get("file_path_contains"), str) and raw.get("file_path_contains").strip() else None,
            adapter=raw.get("adapter").strip() if isinstance(raw.get("adapter"), str) and raw.get("adapter").strip() else None,
            note=raw.get("note").strip() if isinstance(raw.get("note"), str) and raw.get("note").strip() else None,
        )
        out.append(rule)
    return out


def _default_config(path: Path) -> PipelineConfig:
    return PipelineConfig(
        config_path=path,
        exceptions_path=DEFAULT_EXCEPTIONS_PATH,
        target_fields_by_type={"inproceedings": ["url", "pdf", "abstract"]},
        protected_fields={"author", "title", "booktitle", "year"},
        overwrite_existing=False,
        min_abstract_words=25,
        allow_abstract_prefix_match=False,
        report_dir=Path("ops/enrichment-runs"),
        triage_dir=Path("ops/unresolved/enrichment"),
        source_cache_path=Path("ops/enrichment-source-cache.json"),
        openalex_mailto="",
        openalex_api_key=_env_or_dotenv("OPENALEX_API_KEY", ""),
        semantic_scholar_api_key=_env_or_dotenv("SEMANTIC_SCHOLAR_API_KEY", ""),
        semantic_scholar_min_title_score=0.94,
        semantic_scholar_min_confidence=0.91,
        arxiv_min_title_score=0.92,
        arxiv_min_confidence=0.90,
        arxiv_enable_openalex=True,
        arxiv_openalex_max_results=15,
        arxiv_max_results=12,
        timeout_seconds=20.0,
        max_retries=2,
        max_validation_retries=4,
        host_min_interval_seconds=1.0,
        host_min_interval_by_host={
            "api.semanticscholar.org": 1.0,
            "api.openalex.org": 0.1,
            "export.arxiv.org": 5.0,
            "openreview.net": 0.5,
            "api.openreview.net": 1.1,
            "api2.openreview.net": 1.1,
            "proceedings.neurips.cc": 0.2,
            "proceedings.mlr.press": 0.2,
        },
        host_circuit_breaker_threshold=3,
        host_circuit_breaker_cooldown_seconds=180.0,
        backoff_base_seconds=1.0,
        backoff_max_seconds=30.0,
        user_agent="bibliography-enrichment-pipeline/1.0",
        checkpoint_dir=Path("ops/enrichment-checkpoints"),
        checkpoint_flush_every=20,
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
            VenuePolicy(
                name="icml",
                path_contains="conferences/icml/",
                adapter="pmlr",
                allowed_domains={
                    "proceedings.mlr.press",
                    "raw.githubusercontent.com",
                    "icml.cc",
                    "www.icml.cc",
                    "doi.org",
                    "dx.doi.org",
                    "wikidata.org",
                    "www.wikidata.org",
                    "aaai.org",
                    "www.aaai.org",
                    "orkg.org",
                },
            ),
        ],
        exceptions=_load_exception_rules(DEFAULT_EXCEPTIONS_PATH),
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
        if isinstance(defaults.get("exceptions_path"), str) and defaults["exceptions_path"].strip():
            cfg.exceptions_path = Path(defaults["exceptions_path"].strip())
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
        if isinstance(defaults.get("openalex_mailto"), str):
            cfg.openalex_mailto = defaults["openalex_mailto"].strip()
        if isinstance(defaults.get("openalex_api_key"), str):
            candidate = defaults["openalex_api_key"].strip()
            if candidate:
                cfg.openalex_api_key = candidate
        if isinstance(defaults.get("semantic_scholar_api_key"), str):
            candidate = defaults["semantic_scholar_api_key"].strip()
            if candidate:
                cfg.semantic_scholar_api_key = candidate
        if isinstance(defaults.get("semantic_scholar_min_title_score"), (int, float)):
            cfg.semantic_scholar_min_title_score = max(
                0.0,
                min(1.0, float(defaults["semantic_scholar_min_title_score"])),
            )
        if isinstance(defaults.get("semantic_scholar_min_confidence"), (int, float)):
            cfg.semantic_scholar_min_confidence = max(
                0.0,
                min(1.0, float(defaults["semantic_scholar_min_confidence"])),
            )
        if isinstance(defaults.get("arxiv_min_title_score"), (int, float)):
            cfg.arxiv_min_title_score = max(0.0, min(1.0, float(defaults["arxiv_min_title_score"])))
        if isinstance(defaults.get("arxiv_min_confidence"), (int, float)):
            cfg.arxiv_min_confidence = max(0.0, min(1.0, float(defaults["arxiv_min_confidence"])))
        if isinstance(defaults.get("arxiv_enable_openalex"), bool):
            cfg.arxiv_enable_openalex = defaults["arxiv_enable_openalex"]
        if isinstance(defaults.get("arxiv_openalex_max_results"), int):
            cfg.arxiv_openalex_max_results = max(1, min(100, int(defaults["arxiv_openalex_max_results"])))
        if isinstance(defaults.get("arxiv_max_results"), int):
            cfg.arxiv_max_results = max(1, min(100, int(defaults["arxiv_max_results"])))
        if isinstance(defaults.get("timeout_seconds"), (int, float)):
            cfg.timeout_seconds = float(defaults["timeout_seconds"])
        if isinstance(defaults.get("max_retries"), int) and defaults["max_retries"] >= 0:
            cfg.max_retries = defaults["max_retries"]
        if isinstance(defaults.get("max_validation_retries"), int) and defaults["max_validation_retries"] >= 0:
            cfg.max_validation_retries = defaults["max_validation_retries"]
        if isinstance(defaults.get("host_min_interval_seconds"), (int, float)):
            cfg.host_min_interval_seconds = max(0.0, float(defaults["host_min_interval_seconds"]))
        if isinstance(defaults.get("host_circuit_breaker_threshold"), int):
            cfg.host_circuit_breaker_threshold = max(0, defaults["host_circuit_breaker_threshold"])
        if isinstance(defaults.get("host_circuit_breaker_cooldown_seconds"), (int, float)):
            cfg.host_circuit_breaker_cooldown_seconds = max(0.0, float(defaults["host_circuit_breaker_cooldown_seconds"]))
        host_pacing = defaults.get("host_min_interval_by_host")
        if isinstance(host_pacing, dict):
            parsed_host_pacing: dict[str, float] = {}
            for host, interval in host_pacing.items():
                if not isinstance(host, str) or not host.strip():
                    continue
                if not isinstance(interval, (int, float)):
                    continue
                parsed_host_pacing[host.strip().lower()] = max(0.0, float(interval))
            if parsed_host_pacing:
                cfg.host_min_interval_by_host = parsed_host_pacing
        if isinstance(defaults.get("backoff_base_seconds"), (int, float)):
            cfg.backoff_base_seconds = max(0.1, float(defaults["backoff_base_seconds"]))
        if isinstance(defaults.get("backoff_max_seconds"), (int, float)):
            cfg.backoff_max_seconds = max(cfg.backoff_base_seconds, float(defaults["backoff_max_seconds"]))
        if isinstance(defaults.get("user_agent"), str) and defaults["user_agent"].strip():
            cfg.user_agent = defaults["user_agent"].strip()
        if isinstance(defaults.get("checkpoint_dir"), str) and defaults["checkpoint_dir"].strip():
            cfg.checkpoint_dir = Path(defaults["checkpoint_dir"].strip())
        if isinstance(defaults.get("checkpoint_flush_every"), int) and defaults["checkpoint_flush_every"] > 0:
            cfg.checkpoint_flush_every = defaults["checkpoint_flush_every"]

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
            if not (
                isinstance(name, str)
                and name.strip()
                and isinstance(adapter, str)
                and adapter.strip()
                and isinstance(path_contains, str)
            ):
                continue
            normalized_path_contains = path_contains.strip()
            parsed_venues.append(
                VenuePolicy(
                    name=name.strip(),
                    path_contains=normalized_path_contains,
                    adapter=adapter.strip(),
                    allowed_domains={d.strip().lower() for d in allowed_domains if d.strip()},
                )
            )
        if parsed_venues:
            cfg.venues = parsed_venues

    cfg.exceptions = _load_exception_rules(cfg.exceptions_path)

    return cfg
