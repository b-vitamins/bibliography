from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from ..normalization import normalize_text
from .base import AdapterContext

_PMLR_REQUIRED_MARKERS = ('name="citation_title"', 'id="abstract"')
_ICML_YEAR_TO_PMLR_VOLUME = {
    "2013": "28",
    "2014": "32",
    "2015": "37",
    "2016": "48",
    "2017": "70",
    "2018": "80",
    "2019": "97",
    "2020": "119",
    "2021": "139",
    "2022": "162",
    "2023": "202",
    "2024": "235",
}


class PmlrAdapter:
    name = "pmlr"
    provided_fields = {"url", "pdf", "abstract", "title", "doi"}
    fuzzy_title_min_score = 0.90
    fuzzy_title_min_gap = 0.12
    fuzzy_title_second_max = 0.80

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client
        self._volume_index_cache: dict[str, list[tuple[str, str]]] = {}

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        url = str(entry.get("url", "")).lower()
        pdf = str(entry.get("pdf", "")).lower()
        booktitle = str(entry.get("booktitle", "")).lower()
        return (
            "proceedings.mlr.press" in url
            or "proceedings.mlr.press" in pdf
            or "icml" in booktitle
        )

    @staticmethod
    def _canonicalize_https(value: str) -> str:
        url = (value or "").strip()
        if url.startswith("http://proceedings.mlr.press/"):
            return "https://" + url[len("http://") :]
        return url

    @staticmethod
    def _meta_value(page: str, name: str) -> str:
        match = re.search(rf'name="{re.escape(name)}" content="([^"]+)"', page)
        return html.unescape(match.group(1)).strip() if match else ""

    def _source_url_from_entry(self, entry: dict[str, Any]) -> str | None:
        url = str(entry.get("url", "")).strip()
        if not url:
            return None
        if "proceedings.mlr.press" not in url:
            return None
        return self._canonicalize_https(url)

    @staticmethod
    def _volume_from_entry_or_url(entry: dict[str, Any], url: str | None) -> str | None:
        if url:
            parsed = urlparse(url)
            match = re.search(r"/v(\d+)/", parsed.path)
            if match:
                return match.group(1)
        year = str(entry.get("year", "")).strip()
        return _ICML_YEAR_TO_PMLR_VOLUME.get(year)

    def _load_volume_index(self, volume: str) -> list[tuple[str, str]]:
        cached = self._volume_index_cache.get(volume)
        if cached is not None:
            return cached

        listing_url = f"https://proceedings.mlr.press/v{volume}/"
        response = self.http_client.get_text(
            listing_url,
            require_any=[f"/v{volume}/"],
        )
        if response.status_code != 200:
            self._volume_index_cache[volume] = []
            return []

        pattern = re.compile(
            rf'<div class="paper">.*?<p class="title">(.*?)</p>.*?href="(?:https?://proceedings\.mlr\.press)?(/v{re.escape(volume)}/[^"]+\.html)">abs</a>',
            flags=re.S,
        )
        rows: list[tuple[str, str]] = []
        for raw_title, rel_href in pattern.findall(response.text):
            title = re.sub(r"<[^>]+>", " ", raw_title)
            title = re.sub(r"\s+", " ", html.unescape(title)).strip()
            href = urljoin("https://proceedings.mlr.press", rel_href)
            if title and href:
                rows.append((self._canonicalize_https(href), title))

        self._volume_index_cache[volume] = rows
        return rows

    def _resolve_fallback_source_url(self, entry: dict[str, Any], attempted_url: str | None) -> str | None:
        volume = self._volume_from_entry_or_url(entry, attempted_url)
        if not volume:
            return None
        rows = self._load_volume_index(volume)
        if not rows:
            return None

        entry_title = normalize_text(str(entry.get("title", "")))
        if not entry_title:
            return None

        matches = [href for href, title in rows if normalize_text(title) == entry_title]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return None

        scored: list[tuple[float, str]] = []
        for href, title in rows:
            score = SequenceMatcher(a=entry_title, b=normalize_text(title)).ratio()
            scored.append((score, href))
        scored.sort(reverse=True)
        if not scored:
            return None
        top_score, top_href = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if (
            top_score >= self.fuzzy_title_min_score
            and ((top_score - second_score) >= self.fuzzy_title_min_gap or second_score <= self.fuzzy_title_second_max)
        ):
            return top_href
        return None

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        source_url = self._source_url_from_entry(context.entry)
        if not source_url:
            source_url = self._resolve_fallback_source_url(context.entry, None)
            if not source_url:
                return None

        response = self.http_client.get_text(
            source_url,
            require_any=_PMLR_REQUIRED_MARKERS,
        )
        if response.status_code != 200:
            fallback = self._resolve_fallback_source_url(context.entry, source_url)
            if not fallback or fallback == source_url:
                return None
            source_url = fallback
            response = self.http_client.get_text(
                source_url,
                require_any=_PMLR_REQUIRED_MARKERS,
            )
            if response.status_code != 200:
                return None

        text = response.text
        title = self._meta_value(text, "citation_title")
        abstract = self._meta_value(text, "citation_abstract")
        if not abstract:
            abstract_match = re.search(r'<div id="abstract"[^>]*>(.*?)</div>', text, flags=re.S)
            if abstract_match:
                abstract = re.sub(r"<[^>]+>", " ", abstract_match.group(1))
                abstract = re.sub(r"\s+", " ", html.unescape(abstract)).strip()
        pdf = self._canonicalize_https(self._meta_value(text, "citation_pdf_url"))
        doi = self._meta_value(text, "citation_doi")

        fields: dict[str, str] = {"url": self._canonicalize_https(source_url)}
        if title:
            fields["title"] = title
        if abstract:
            fields["abstract"] = abstract
        if pdf:
            fields["pdf"] = pdf
        if doi:
            fields["doi"] = doi
        if len(fields) <= 1:
            return None

        return SourceRecord(
            adapter=self.name,
            source_url=source_url,
            fetched_at=response.fetched_at or now_iso(),
            fields=fields,
        )
