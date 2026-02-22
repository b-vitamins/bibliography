from __future__ import annotations

from core.http_client import CachedHttpClient

from .neurips import NeuripsProceedingsCatalogAdapter
from .openreview import OpenReviewConferenceCatalogAdapter
from .pmlr import PmlrVolumeCatalogAdapter


def build_catalog_adapter_registry(http_client: CachedHttpClient) -> dict[str, object]:
    adapters = [
        OpenReviewConferenceCatalogAdapter(http_client),
        NeuripsProceedingsCatalogAdapter(http_client),
        PmlrVolumeCatalogAdapter(http_client),
    ]
    return {adapter.name: adapter for adapter in adapters}

