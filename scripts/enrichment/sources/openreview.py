from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from .base import AdapterContext

_META_RE_TEMPLATE = r'name="{name}" content="([^"]+)"'


class OpenReviewAdapter:
    name = "openreview"
    provided_fields = {"url", "pdf", "abstract", "title", "booktitle", "author"}

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        url = str(entry.get("url", "")).lower()
        pdf = str(entry.get("pdf", "")).lower()
        return "openreview.net" in url or "openreview.net" in pdf

    @staticmethod
    def _meta_value(page: str, name: str) -> str:
        pattern = _META_RE_TEMPLATE.format(name=re.escape(name))
        match = re.search(pattern, page)
        return html.unescape(match.group(1)).strip() if match else ""

    @staticmethod
    def _meta_values(page: str, name: str) -> list[str]:
        pattern = _META_RE_TEMPLATE.format(name=re.escape(name))
        values = [html.unescape(v).strip() for v in re.findall(pattern, page)]
        return [v for v in values if v]

    @staticmethod
    def _extract_forum_id(value: str) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        ids = query.get("id", [])
        if ids:
            return ids[0].strip() or None
        if parsed.path.startswith("/forum") and "id=" in value:
            return value.split("id=", 1)[1].split("&", 1)[0].strip() or None
        return None

    def _forum_id_from_entry(self, entry: dict[str, Any]) -> str | None:
        for field in ["url", "pdf"]:
            maybe = self._extract_forum_id(str(entry.get(field, "")).strip())
            if maybe:
                return maybe
        return None

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        forum_id = self._forum_id_from_entry(context.entry)
        if not forum_id:
            return None

        source_url = f"https://openreview.net/forum?id={forum_id}"
        response = self.http_client.get_text(source_url)
        if response.status_code != 200:
            return None

        title = self._meta_value(response.text, "citation_title")
        abstract = self._meta_value(response.text, "citation_abstract")
        pdf = self._meta_value(response.text, "citation_pdf_url")
        booktitle = self._meta_value(response.text, "citation_conference_title")
        authors = self._meta_values(response.text, "citation_author")

        fields: dict[str, str] = {
            "url": source_url,
        }
        if title:
            fields["title"] = title
        if abstract:
            fields["abstract"] = abstract
        if pdf:
            fields["pdf"] = pdf
        else:
            fields["pdf"] = f"https://openreview.net/pdf?id={forum_id}"
        if booktitle:
            fields["booktitle"] = booktitle
        if authors:
            fields["author"] = " and ".join(authors)

        return SourceRecord(
            adapter=self.name,
            source_url=source_url,
            fetched_at=response.fetched_at or now_iso(),
            fields=fields,
        )
