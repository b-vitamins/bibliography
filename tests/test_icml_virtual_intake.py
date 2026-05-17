from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.http_client import HttpResponse  # noqa: E402
from intake.models import IntakeTarget  # noqa: E402
from intake.sources.base import CatalogContext  # noqa: E402
from intake.sources.icml import IcmlVirtualCatalogAdapter  # noqa: E402


class FakeHttpClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses

    def get_text(self, url: str, **_kwargs: object) -> HttpResponse:
        payload = self.responses.get(url)
        if payload is None:
            return HttpResponse(url=url, status_code=404, text="", fetched_at="2026-05-12T00:00:00+00:00", from_cache=False)
        return HttpResponse(
            url=url,
            status_code=200,
            text=json.dumps(payload),
            fetched_at="2026-05-12T00:00:00+00:00",
            from_cache=False,
        )


class IcmlVirtualCatalogAdapterTests(unittest.TestCase):
    def test_fetch_catalog_uses_official_virtual_json(self) -> None:
        papers_url = "https://icml.cc/static/virtual/data/icml-2026-orals-posters.json"
        abstracts_url = "https://icml.cc/static/virtual/data/icml-2026-abstracts.json"
        client = FakeHttpClient(
            {
                papers_url: {
                    "count": 3,
                    "results": [
                        {
                            "id": 64822,
                            "name": "A &amp; B Paper",
                            "authors": [{"fullname": "Ada Lovelace"}, {"fullname": "Grace Hopper"}],
                            "decision": "Accept (spotlight)",
                            "eventtype": "Poster",
                            "visible": True,
                            "virtualsite_url": "/virtual/2026/poster/64822",
                            "paper_url": "https://openreview.net/forum?id=abc123",
                        },
                        {
                            "id": 1,
                            "name": "Rejected",
                            "authors": [{"fullname": "Example Author"}],
                            "decision": "Reject",
                            "eventtype": "Poster",
                            "visible": True,
                            "virtualsite_url": "/virtual/2026/poster/1",
                        },
                        {
                            "id": 2,
                            "name": "Session",
                            "authors": [{"fullname": "Example Author"}],
                            "decision": "Accept",
                            "eventtype": "Talk",
                            "visible": True,
                            "virtualsite_url": "/virtual/2026/session/2",
                        },
                    ],
                },
                abstracts_url: {"64822": "The abstract."},
            }
        )
        adapter = IcmlVirtualCatalogAdapter(client)  # type: ignore[arg-type]
        target = IntakeTarget(
            venue="icml",
            year=2026,
            file_path="conferences/icml/2026.bib",
            adapter=adapter.name,
            params={"booktitle": "ICML", "publisher": "OpenReview.net"},
        )

        snapshot = adapter.fetch_catalog(CatalogContext(target=target))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.expected_count, 3)
        self.assertEqual(len(snapshot.records), 1)
        record = snapshot.records[0]
        self.assertEqual(record.source_id, "64822")
        self.assertEqual(record.title, "A & B Paper")
        self.assertEqual(record.authors, ["Ada Lovelace", "Grace Hopper"])
        self.assertEqual(record.url, "https://icml.cc/virtual/2026/poster/64822")
        self.assertEqual(record.abstract, "The abstract.")
        self.assertEqual(record.extra_fields["openreview"], "https://openreview.net/forum?id=abc123")
        self.assertEqual(record.extra_fields["decision"], "Accept (spotlight)")

    def test_source_id_from_entry_accepts_sourceid_or_poster_url(self) -> None:
        adapter = IcmlVirtualCatalogAdapter(FakeHttpClient({}))  # type: ignore[arg-type]

        self.assertEqual(adapter.source_id_from_entry({"sourceid": "icml_virtual_catalog:64822"}), "64822")
        self.assertEqual(adapter.source_id_from_entry({"url": "https://icml.cc/virtual/2026/poster/64822"}), "64822")


if __name__ == "__main__":
    unittest.main()
