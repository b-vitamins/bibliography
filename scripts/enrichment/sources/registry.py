from __future__ import annotations

from ..config import PipelineConfig
from ..http_client import CachedHttpClient
from .arxiv import ArxivAdapter
from .neurips import NeuripsProceedingsAdapter
from .openreview import OpenReviewAdapter
from .pmlr import PmlrAdapter
from .semanticscholar import SemanticScholarAdapter


def build_adapter_registry(http_client: CachedHttpClient, cfg: PipelineConfig) -> dict[str, object]:
    adapters = [
        OpenReviewAdapter(http_client),
        NeuripsProceedingsAdapter(http_client),
        PmlrAdapter(http_client),
        ArxivAdapter(
            http_client=http_client,
            min_title_score=cfg.arxiv_min_title_score,
            min_confidence=cfg.arxiv_min_confidence,
            enable_openalex=cfg.arxiv_enable_openalex,
            openalex_max_results=cfg.arxiv_openalex_max_results,
            arxiv_max_results=cfg.arxiv_max_results,
            openalex_mailto=cfg.openalex_mailto,
            openalex_api_key=cfg.openalex_api_key,
        ),
        SemanticScholarAdapter(
            http_client=http_client,
            min_title_score=cfg.semantic_scholar_min_title_score,
            min_confidence=cfg.semantic_scholar_min_confidence,
            api_key=cfg.semantic_scholar_api_key,
        ),
    ]
    return {adapter.name: adapter for adapter in adapters}
