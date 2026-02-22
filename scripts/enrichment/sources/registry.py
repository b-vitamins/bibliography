from __future__ import annotations

from ..config import PipelineConfig
from ..http_client import CachedHttpClient
from .arxiv import ArxivAdapter
from .neurips import NeuripsProceedingsAdapter
from .openreview import OpenReviewAdapter
from .pmlr import PmlrAdapter


def build_adapter_registry(http_client: CachedHttpClient, cfg: PipelineConfig) -> dict[str, object]:
    adapters = [
        OpenReviewAdapter(http_client),
        NeuripsProceedingsAdapter(http_client),
        PmlrAdapter(http_client),
        ArxivAdapter(
            http_client=http_client,
            min_title_score=cfg.arxiv_min_title_score,
            min_confidence=cfg.arxiv_min_confidence,
            openalex_max_results=cfg.arxiv_openalex_max_results,
            arxiv_max_results=cfg.arxiv_max_results,
            openalex_mailto=cfg.openalex_mailto,
            openalex_api_key=cfg.openalex_api_key,
        ),
    ]
    return {adapter.name: adapter for adapter in adapters}
