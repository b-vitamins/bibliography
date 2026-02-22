from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from core.http_client import CachedHttpClient
from core.normalization import normalize_text
from core.time_utils import now_iso

from ..models import CatalogSnapshot, IntakeRecord
from .base import CatalogContext

_NEURIPS_ABSTRACT_MARKERS = ('class="paper-abstract"',)
_NEURIPS_LISTING_LINK_RE = re.compile(
    r'href="(/paper_files/paper/(?P<year>\d{4})/hash/(?P<hash>[0-9a-f]{32})-Abstract(?:-[^"]+)?\.html)"[^>]*>(?P<title>.*?)</a>',
    flags=re.S,
)
_NEURIPS_HASH_RE = re.compile(r"/hash/([0-9a-f]{32})-Abstract")
_NEURIPS_PDF_HASH_RE = re.compile(r"/file/([0-9a-f]{32})-Paper")


class NeuripsProceedingsCatalogAdapter:
    name = "neurips_proceedings_catalog"

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    @staticmethod
    def _normalize_html_text(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _meta_value(page: str, name: str) -> str:
        match = re.search(rf'name="{re.escape(name)}" content="([^"]+)"', page)
        return html.unescape(match.group(1)).strip() if match else ""

    @classmethod
    def _extract_listing_rows(cls, text: str, year: int) -> list[tuple[str, str, str]]:
        rows_by_id: dict[str, tuple[str, str, str]] = {}
        for match in _NEURIPS_LISTING_LINK_RE.finditer(text):
            row_year = int(match.group("year"))
            if row_year != year:
                continue
            source_id = match.group("hash")
            rel = match.group(1)
            title = cls._normalize_html_text(match.group("title"))
            if not source_id or not rel or not title:
                continue
            if source_id in rows_by_id:
                continue
            rows_by_id[source_id] = (source_id, urljoin("https://proceedings.neurips.cc", rel), title)
        return list(rows_by_id.values())

    @classmethod
    def _record_from_page(
        cls,
        source_id: str,
        source_url: str,
        page: str,
        year: int,
        booktitle: str,
        publisher: str,
    ) -> IntakeRecord | None:
        title = cls._meta_value(page, "citation_title")
        if not title:
            heading = re.search(r"<h4>(.*?)</h4>", page, flags=re.S)
            title = cls._normalize_html_text(heading.group(1)) if heading else ""
        if not title:
            return None

        abstract = ""
        abstract_match = re.search(
            r'<p class="paper-abstract">\s*(?:<p>)?(.*?)(?:</p>\s*</p>|</p>)',
            page,
            flags=re.S,
        )
        if abstract_match:
            abstract = cls._normalize_html_text(abstract_match.group(1))

        pdf = cls._meta_value(page, "citation_pdf_url")
        if not pdf:
            pdf_match = re.search(r'href="([^"]+-Paper(?:-[^"]+)?\.pdf)"', page)
            if pdf_match:
                pdf = urljoin(source_url, pdf_match.group(1))

        doi = cls._meta_value(page, "citation_doi")
        if not doi:
            doi_match = re.search(r'class="paper-doi">([^<]+)</a>', page)
            doi = cls._normalize_html_text(doi_match.group(1)) if doi_match else ""

        authors: list[str] = []
        for author in re.findall(r'name="citation_author" content="([^"]+)"', page):
            text = html.unescape(author).strip()
            if text:
                authors.append(text)

        if not authors:
            return None

        return IntakeRecord(
            source_id=source_id,
            source_url=source_url,
            title=title,
            authors=authors,
            year=year,
            booktitle=booktitle,
            publisher=publisher,
            url=source_url,
            pdf=pdf or None,
            abstract=abstract or None,
            doi=doi or None,
            extra_fields={"source_adapter": cls.name},
        )

    def fetch_catalog(self, context: CatalogContext) -> CatalogSnapshot | None:
        target = context.target
        purpose = context.purpose
        max_records = max(0, int(context.max_records))
        year = target.year
        params = target.params
        booktitle = str(params.get("booktitle", "")).strip() or "Advances in Neural Information Processing Systems"
        publisher = str(params.get("publisher", "")).strip() or "Curran Associates, Inc."

        listing_url = f"https://proceedings.neurips.cc/paper_files/paper/{year}"
        listing = self.http_client.get_text(listing_url, require_any=[f"/paper_files/paper/{year}/hash/"])
        if listing.status_code != 200:
            return None

        rows = self._extract_listing_rows(listing.text, year)
        if not rows:
            return None
        if max_records and len(rows) > max_records:
            rows = rows[:max_records]

        if purpose in {"discover", "plan"}:
            stubs = [
                IntakeRecord(
                    source_id=source_id,
                    source_url=source_url,
                    title=title,
                    authors=["unknown"],
                    year=year,
                    booktitle=booktitle,
                    publisher=publisher,
                    url=source_url,
                    extra_fields={"source_adapter": self.name, "discovery_only": "true"},
                )
                for source_id, source_url, title in rows
            ]
            return CatalogSnapshot(
                adapter=self.name,
                target=target,
                fetched_at=listing.fetched_at or now_iso(),
                records=stubs,
                expected_count=len(rows),
                metadata={
                    "listing_url": listing_url,
                    "listing_rows": len(rows),
                    "discover_mode": purpose == "discover",
                    "plan_mode": purpose == "plan",
                },
            )

        records: list[IntakeRecord] = []
        for source_id, source_url, _title in rows:
            page = self.http_client.get_text(source_url, require_any=_NEURIPS_ABSTRACT_MARKERS)
            if page.status_code != 200:
                continue
            record = self._record_from_page(
                source_id=source_id,
                source_url=source_url,
                page=page.text,
                year=year,
                booktitle=booktitle,
                publisher=publisher,
            )
            if record is not None:
                records.append(record)

        if not records:
            return None

        # Deterministic order and mild de-dup by source id.
        by_id: dict[str, IntakeRecord] = {}
        for record in records:
            existing = by_id.get(record.source_id)
            if existing is None:
                by_id[record.source_id] = record
                continue
            if (not existing.abstract) and record.abstract:
                by_id[record.source_id] = record

        normalized = sorted(by_id.values(), key=lambda r: normalize_text(r.title))
        return CatalogSnapshot(
            adapter=self.name,
            target=target,
            fetched_at=listing.fetched_at or now_iso(),
            records=normalized,
            expected_count=len(rows),
            metadata={
                "listing_url": listing_url,
                "listing_rows": len(rows),
                "fetched_records": len(normalized),
            },
        )

    def source_id_from_entry(self, entry: dict[str, Any]) -> str | None:
        sourceid = str(entry.get("sourceid", "")).strip()
        if sourceid.lower().startswith(f"{self.name}:"):
            suffix = sourceid.split(":", 1)[1].strip()
            if suffix:
                return suffix

        for field in ("url", "pdf"):
            value = str(entry.get(field, "")).strip()
            match = _NEURIPS_HASH_RE.search(value)
            if match:
                return match.group(1)
            match = _NEURIPS_PDF_HASH_RE.search(value)
            if match:
                return match.group(1)
        return None

    def supports(self, file_path) -> bool:
        path = str(file_path).lower()
        return "conferences/neurips/" in path
