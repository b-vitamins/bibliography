"""Modular, source-grounded bibliography enrichment pipeline."""

from .config import PipelineConfig, load_pipeline_config
from .engine import EnrichmentEngine

__all__ = ["PipelineConfig", "EnrichmentEngine", "load_pipeline_config"]
