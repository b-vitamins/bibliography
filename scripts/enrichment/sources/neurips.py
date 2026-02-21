from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from ..normalization import normalize_text
from .base import AdapterContext


class NeuripsProceedingsAdapter:
    name = "neurips_proceedings"
    provided_fields = {"url", "pdf", "abstract", "title", "doi"}

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client
        self._year_index_cache: dict[str, list[tuple[str, str]]] = {}

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        url = str(entry.get("url", "")).lower()
        pdf = str(entry.get("pdf", "")).lower()
        file_hint = str(file_path).lower()
        booktitle = str(entry.get("booktitle", "")).lower()
        year_raw = str(entry.get("year", "")).strip()
        year_ok = year_raw.isdigit() and int(year_raw) >= 2020
        return (
            "proceedings.neurips.cc" in url
            or "neurips.cc" in url
            or "papers.nips.cc" in url
            or "proceedings.neurips.cc" in pdf
            or "neurips.cc" in pdf
            or (
                "conferences/neurips/" in file_hint
                and "advances in neural information processing systems" in booktitle
                and year_ok
            )
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

    @staticmethod
    def _year_from_entry_or_url(entry: dict[str, Any], url: str | None) -> str | None:
        year_raw = str(entry.get("year", "")).strip()
        if year_raw.isdigit():
            return year_raw
        if url:
            match = re.search(r"/paper/(\d{4})/", url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _hash_from_url(url: str | None) -> str | None:
        if not url:
            return None
        match = re.search(r"/hash/([0-9a-f]{32})-Abstract-", url)
        if match:
            return match.group(1)
        return None

    def _load_year_index(self, year: str) -> list[tuple[str, str]]:
        cached = self._year_index_cache.get(year)
        if cached is not None:
            return cached

        listing_url = f"https://proceedings.neurips.cc/paper_files/paper/{year}"
        response = self.http_client.get_text(listing_url)
        if response.status_code != 200:
            self._year_index_cache[year] = []
            return []

        pattern = re.compile(
            rf'href="(/paper_files/paper/{re.escape(year)}/hash/[0-9a-f]{{32}}-Abstract-[^"]+\.html)"[^>]*>(.*?)</a>',
            flags=re.S,
        )
        rows: list[tuple[str, str]] = []
        for rel_href, raw_title in pattern.findall(response.text):
            href = urljoin("https://proceedings.neurips.cc", rel_href)
            title = self._normalize_text(raw_title)
            if title:
                rows.append((href, title))

        self._year_index_cache[year] = rows
        return rows

    def _resolve_fallback_source_url(self, entry: dict[str, Any], attempted_url: str | None) -> str | None:
        year = self._year_from_entry_or_url(entry, attempted_url)
        if not year:
            return None

        rows = self._load_year_index(year)
        if not rows:
            return None

        attempted_hash = self._hash_from_url(attempted_url)
        if attempted_hash:
            for href, _title in rows:
                if f"/hash/{attempted_hash}-Abstract-" in href:
                    return href

        entry_title = normalize_text(str(entry.get("title", "")))
        if entry_title:
            matches = [href for href, title in rows if normalize_text(title) == entry_title]
            if len(matches) == 1:
                return matches[0]

        return None

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        source_url = self._source_url_from_entry(context.entry)
        if not source_url:
            source_url = self._resolve_fallback_source_url(context.entry, None)
            if not source_url:
                return None

        response = self.http_client.get_text(source_url)
        if response.status_code != 200:
            fallback = self._resolve_fallback_source_url(context.entry, source_url)
            if not fallback or fallback == source_url:
                return None
            source_url = fallback
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
