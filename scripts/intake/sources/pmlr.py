from __future__ import annotations

import html
import re
from typing import Any

import bibtexparser

from core.http_client import CachedHttpClient
from core.normalization import normalize_text
from core.time_utils import now_iso

from ..models import CatalogSnapshot, IntakeRecord
from .base import CatalogContext

_PMLR_URL_RE = re.compile(r"https?://proceedings\.mlr\.press/v(?P<vol>\d+)/(?P<slug>[^/]+)\.html", re.I)


class PmlrVolumeCatalogAdapter:
    name = "pmlr_volume_catalog"

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    @staticmethod
    def _canonicalize_https(value: str) -> str:
        url = (value or "").strip()
        if url.startswith("http://proceedings.mlr.press/"):
            return "https://" + url[len("http://") :]
        return url

    @staticmethod
    def _volume_from_params(params: dict[str, Any], year: int) -> str | None:
        if "volume" in params:
            value = str(params.get("volume", "")).strip()
            if value.isdigit():
                return value
        volume_by_year = params.get("volume_by_year")
        if isinstance(volume_by_year, dict):
            raw = volume_by_year.get(str(year))
            if isinstance(raw, (int, float)):
                return str(int(raw))
            if isinstance(raw, str) and raw.strip().isdigit():
                return raw.strip()
        return None

    @classmethod
    def _source_id_from_url(cls, value: str) -> str | None:
        match = _PMLR_URL_RE.search(value or "")
        if not match:
            return None
        return match.group("slug").strip().lower() or None

    def fetch_catalog(self, context: CatalogContext) -> CatalogSnapshot | None:
        target = context.target
        max_records = max(0, int(context.max_records))
        params = target.params
        volume = self._volume_from_params(params, target.year)
        if not volume:
            return None

        booktitle = str(params.get("booktitle", "")).strip() or "ICML"
        publisher = str(params.get("publisher", "")).strip() or "PMLR"

        bib_url = f"https://proceedings.mlr.press/v{volume}/assets/bib/bibliography.bib"
        response = self.http_client.get_text(bib_url, require_any=["@InProceedings", f"v{volume}"])
        if response.status_code != 200:
            return None

        try:
            library = bibtexparser.loads(response.text)
        except Exception:
            return None

        records: dict[str, IntakeRecord] = {}
        for entry in library.entries:
            if str(entry.get("ENTRYTYPE", "")).lower() != "inproceedings":
                continue
            url = self._canonicalize_https(str(entry.get("url", "")).strip())
            source_id = self._source_id_from_url(url)
            title = str(entry.get("title", "")).strip()
            author = str(entry.get("author", "")).strip()
            if not source_id or not title or not author:
                continue
            authors = [a.strip() for a in author.split(" and ") if a.strip()]
            if not authors:
                continue
            pdf = self._canonicalize_https(str(entry.get("pdf", "")).strip()) or None
            abstract = str(entry.get("abstract", "")).strip() or None
            doi = str(entry.get("doi", "")).strip() or None
            records[source_id] = IntakeRecord(
                source_id=source_id,
                source_url=url,
                title=html.unescape(title).strip(),
                authors=authors,
                year=target.year,
                booktitle=booktitle,
                publisher=publisher,
                url=url,
                pdf=pdf,
                abstract=abstract,
                doi=doi,
                extra_fields={"source_adapter": self.name, "volume": str(volume)},
            )

        if not records:
            return None

        records_list = sorted(records.values(), key=lambda r: normalize_text(r.title))
        if max_records and len(records_list) > max_records:
            records_list = records_list[:max_records]

        return CatalogSnapshot(
            adapter=self.name,
            target=target,
            fetched_at=response.fetched_at or now_iso(),
            records=records_list,
            expected_count=len(records_list),
            metadata={
                "volume": str(volume),
                "bib_url": bib_url,
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
            found = self._source_id_from_url(value)
            if found:
                return found
        return None

    def supports(self, file_path) -> bool:
        path = str(file_path).lower()
        return "conferences/icml/" in path
