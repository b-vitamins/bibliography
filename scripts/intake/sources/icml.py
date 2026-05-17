from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from core.http_client import CachedHttpClient
from core.normalization import normalize_text
from core.time_utils import now_iso

from ..models import CatalogSnapshot, IntakeRecord
from .base import CatalogContext

_ICML_POSTER_URL_RE = re.compile(
    r"https?://(?:www\.)?icml\.cc/virtual/(?P<year>\d{4})/poster/(?P<id>\d+)",
    re.I,
)


class IcmlVirtualCatalogAdapter:
    name = "icml_virtual_catalog"

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        text = html.unescape(str(value))
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _url(base_url: str, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        return urljoin(base_url.rstrip("/") + "/", raw)

    @staticmethod
    def _format_url_template(template: str, *, year: int, venue: str) -> str:
        return template.format(year=year, venue=venue, venue_lower=venue.lower(), venue_upper=venue.upper())

    @classmethod
    def _authors(cls, row: dict[str, Any]) -> list[str]:
        raw_authors = row.get("authors")
        if not isinstance(raw_authors, list):
            return []
        out: list[str] = []
        for raw in raw_authors:
            if isinstance(raw, dict):
                name = cls._text(raw.get("fullname"))
            else:
                name = cls._text(raw)
            if name:
                out.append(name)
        return out

    @classmethod
    def _eventmedia_url(cls, row: dict[str, Any], *, name: str | None = None, pdf_only: bool = False) -> str:
        raw_media = row.get("eventmedia")
        if not isinstance(raw_media, list):
            return ""
        for raw in raw_media:
            if not isinstance(raw, dict):
                continue
            if raw.get("visible") is False:
                continue
            label = cls._text(raw.get("name")).lower()
            uri = cls._text(raw.get("uri"))
            if not uri:
                continue
            if name is not None and name.lower() not in label:
                continue
            if pdf_only and ".pdf" not in urlparse(uri).path.lower():
                continue
            return uri
        return ""

    @classmethod
    def _paper_url(cls, row: dict[str, Any]) -> str:
        return cls._text(row.get("paper_url")) or cls._eventmedia_url(row, name="openreview")

    @classmethod
    def _pdf_url(cls, row: dict[str, Any]) -> str:
        return cls._text(row.get("paper_pdf_url")) or cls._eventmedia_url(row, name="pdf", pdf_only=True)

    @staticmethod
    def _openreview_id(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in {"openreview.net", "www.openreview.net"}:
            return ""
        ids = parse_qs(parsed.query).get("id", [])
        return ids[0].strip() if ids else ""

    def fetch_catalog(self, context: CatalogContext) -> CatalogSnapshot | None:
        target = context.target
        params = target.params
        max_records = max(0, int(context.max_records))
        base_url = str(params.get("base_url", "https://icml.cc")).strip() or "https://icml.cc"
        papers_url_template = str(
            params.get(
                "papers_json_url_template",
                "{base_url}/static/virtual/data/icml-{year}-orals-posters.json",
            )
        ).strip()
        abstracts_url_template = str(
            params.get(
                "abstracts_json_url_template",
                "{base_url}/static/virtual/data/icml-{year}-abstracts.json",
            )
        ).strip()
        papers_url = self._format_url_template(
            papers_url_template.replace("{base_url}", base_url.rstrip("/")),
            year=target.year,
            venue=target.venue,
        )
        abstracts_url = self._format_url_template(
            abstracts_url_template.replace("{base_url}", base_url.rstrip("/")),
            year=target.year,
            venue=target.venue,
        )
        booktitle = str(params.get("booktitle", "")).strip() or "ICML"
        publisher = str(params.get("publisher", "")).strip() or "OpenReview.net"

        response = self.http_client.get_text(papers_url, require_any=['"count"', '"results"'])
        if response.status_code != 200:
            return None
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            return None
        rows = payload.get("results")
        if not isinstance(rows, list):
            return None

        abstracts: dict[str, str] = {}
        abstracts_response = self.http_client.get_text(abstracts_url, require_any=("{", "}"))
        if abstracts_response.status_code == 200:
            try:
                raw_abstracts = json.loads(abstracts_response.text)
            except json.JSONDecodeError:
                raw_abstracts = {}
            if isinstance(raw_abstracts, dict):
                for key, value in raw_abstracts.items():
                    abstract = self._text(value)
                    if abstract:
                        abstracts[str(key).strip()] = abstract

        records: dict[str, IntakeRecord] = {}
        skipped_non_accept = 0
        skipped_non_poster = 0
        skipped_incomplete = 0
        decision_counts: dict[str, int] = {}

        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("visible") is False:
                continue
            if self._text(row.get("eventtype")).lower() != "poster":
                skipped_non_poster += 1
                continue
            decision = self._text(row.get("decision"))
            if decision:
                decision_counts[decision] = decision_counts.get(decision, 0) + 1
            if decision and not decision.lower().startswith("accept"):
                skipped_non_accept += 1
                continue

            source_id = self._text(row.get("id"))
            title = self._text(row.get("name"))
            authors = self._authors(row)
            virtualsite_url = self._url(base_url, row.get("virtualsite_url"))
            if not source_id or not title or not authors or not virtualsite_url:
                skipped_incomplete += 1
                continue

            paper_url = self._paper_url(row)
            pdf_url = self._pdf_url(row)
            abstract = abstracts.get(source_id) or self._text(row.get("abstract"))
            extra_fields: dict[str, str] = {"source_adapter": self.name}
            if decision:
                extra_fields["decision"] = decision
            openreview_id = self._openreview_id(paper_url)
            if paper_url and openreview_id:
                extra_fields["openreview"] = paper_url

            records[source_id] = IntakeRecord(
                source_id=source_id,
                source_url=virtualsite_url,
                title=title,
                authors=authors,
                year=target.year,
                booktitle=booktitle,
                publisher=publisher,
                url=virtualsite_url,
                pdf=pdf_url or None,
                abstract=abstract or None,
                extra_fields=extra_fields,
            )
            if max_records and len(records) >= max_records:
                break

        if not records:
            return None

        records_list = sorted(records.values(), key=lambda r: (normalize_text(r.title), r.source_id))
        expected_count = payload.get("count")
        if not isinstance(expected_count, int):
            expected_count = len(records_list)
        if max_records:
            expected_count = min(expected_count, max_records)

        return CatalogSnapshot(
            adapter=self.name,
            target=target,
            fetched_at=response.fetched_at or now_iso(),
            records=records_list,
            expected_count=expected_count,
            metadata={
                "papers_url": papers_url,
                "abstracts_url": abstracts_url,
                "source_count": len(rows),
                "abstract_count": len(abstracts),
                "decision_counts": decision_counts,
                "skipped_non_accept": skipped_non_accept,
                "skipped_non_poster": skipped_non_poster,
                "skipped_incomplete": skipped_incomplete,
            },
        )

    def source_id_from_entry(self, entry: dict[str, Any]) -> str | None:
        sourceid = str(entry.get("sourceid", "")).strip()
        if sourceid.lower().startswith(f"{self.name}:"):
            suffix = sourceid.split(":", 1)[1].strip()
            if suffix:
                return suffix
        for field in ("url",):
            value = str(entry.get(field, "")).strip()
            match = _ICML_POSTER_URL_RE.search(value)
            if match:
                return match.group("id")
        return None

    def supports(self, file_path) -> bool:
        path = str(file_path).lower()
        return "conferences/icml/" in path
