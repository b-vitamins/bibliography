from __future__ import annotations

from ..http_client import CachedHttpClient
from .neurips import NeuripsProceedingsAdapter
from .openreview import OpenReviewAdapter
from .pmlr import PmlrAdapter


def build_adapter_registry(http_client: CachedHttpClient) -> dict[str, object]:
    adapters = [
        OpenReviewAdapter(http_client),
        NeuripsProceedingsAdapter(http_client),
        PmlrAdapter(http_client),
    ]
    return {adapter.name: adapter for adapter in adapters}
