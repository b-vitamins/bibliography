from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from .base import AdapterContext


class NeuripsProceedingsAdapter:
    name = "neurips_proceedings"
    provided_fields = {"url", "pdf", "abstract", "title", "doi"}

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        url = str(entry.get("url", "")).lower()
        pdf = str(entry.get("pdf", "")).lower()
        return (
            "proceedings.neurips.cc" in url
            or "neurips.cc" in url
            or "papers.nips.cc" in url
            or "proceedings.neurips.cc" in pdf
            or "neurips.cc" in pdf
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _abstract_url_from_pdf(pdf_url: str) -> str | None:
        parsed = urlparse(pdf_url)
        if not parsed.netloc:
            return None
        match = re.search(r"/file/([0-9a-f]{32})-Paper-([A-Za-z0-9_]+)\.pdf", parsed.path)
        if not match:
            return None
        paper_hash = match.group(1)
        track = match.group(2)
        year_match = re.search(r"/paper/(\d{4})/", parsed.path)
        if not year_match:
            return None
        year = year_match.group(1)
        return (
            f"https://proceedings.neurips.cc/paper_files/paper/{year}/hash/"
            f"{paper_hash}-Abstract-{track}.html"
        )

    def _source_url_from_entry(self, entry: dict[str, Any]) -> str | None:
        url = str(entry.get("url", "")).strip()
        if "paper_files/paper/" in url and "-Abstract-" in url and url.endswith(".html"):
            return url

        pdf = str(entry.get("pdf", "")).strip()
        from_pdf = self._abstract_url_from_pdf(pdf)
        if from_pdf:
            return from_pdf

        return None

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        source_url = self._source_url_from_entry(context.entry)
        if not source_url:
            return None

        response = self.http_client.get_text(source_url)
        if response.status_code != 200:
            return None

        text = response.text

        title_match = re.search(r"<h4>(.*?)</h4>", text, flags=re.S)
        title = self._normalize_text(title_match.group(1)) if title_match else ""

        abstract_match = re.search(
            r'<p class="paper-abstract">\s*(?:<p>)?(.*?)(?:</p>\s*</p>|</p>)',
            text,
            flags=re.S,
        )
        abstract = self._normalize_text(abstract_match.group(1)) if abstract_match else ""

        doi_match = re.search(r'class="paper-doi">([^<]+)</a>', text)
        doi = self._normalize_text(doi_match.group(1)) if doi_match else ""

        pdf_match = re.search(r'href="([^"]+-Paper-[^"]+\.pdf)"', text)
        pdf = urljoin(source_url, pdf_match.group(1)) if pdf_match else ""

        fields: dict[str, str] = {"url": source_url}
        if title:
            fields["title"] = title
        if abstract:
            fields["abstract"] = abstract
        if doi:
            fields["doi"] = doi
        if pdf:
            fields["pdf"] = pdf

        return SourceRecord(
            adapter=self.name,
            source_url=source_url,
            fetched_at=response.fetched_at or now_iso(),
            fields=fields,
        )
