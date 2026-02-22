from __future__ import annotations

import json
import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from ..normalization import normalize_text
from .base import AdapterContext

_META_RE_TEMPLATE = r'name="{name}" content="([^"]+)"'
_OPENREVIEW_REQUIRED_MARKERS = ('name="citation_title"',)
_OPENREVIEW_REJECT_MARKERS = (
    "the server responded with the following message",
    "too many requests:",
)
_OPENREVIEW_API_PAGE_LIMIT = 1000
_OPENREVIEW_BULK_INVITATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("api2", "ICLR.cc/{year}/Conference/-/Submission"),
    ("api2", "ICLR.cc/{year}/Conference/-/Post_Submission"),
    ("api1", "ICLR.cc/{year}/Conference/-/Blind_Submission"),
    ("api1", "ICLR.cc/{year}/Conference/-/Submission"),
    ("api1", "ICLR.cc/{year}/conference/-/submission"),
    ("api1", "ICLR.cc/{year}/conference/-/blind_submission"),
)


class OpenReviewAdapter:
    name = "openreview"
    provided_fields = {"url", "pdf", "abstract", "title", "booktitle", "author"}

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client
        self._bulk_records_by_file: dict[str, dict[str, SourceRecord]] = {}
        self._bulk_title_index_by_file: dict[str, dict[str, SourceRecord | None]] = {}
        self._bulk_attempted_files: set[str] = set()

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        path = str(file_path).lower()
        if "conferences/iclr/" in path:
            publisher = str(entry.get("publisher", "")).lower()
            if "openreview" in publisher:
                return True
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

    @staticmethod
    def _year_from_file_path(file_path: Path) -> str | None:
        year = file_path.stem.strip()
        if len(year) == 4 and year.isdigit():
            return year
        return None

    @staticmethod
    def _unwrap_content_value(value: Any) -> Any:
        if isinstance(value, dict) and "value" in value:
            return value.get("value")
        return value

    @classmethod
    def _content_text(cls, content: dict[str, Any], key: str) -> str:
        raw = cls._unwrap_content_value(content.get(key))
        if isinstance(raw, str):
            return raw.strip()
        return ""

    @classmethod
    def _content_list(cls, content: dict[str, Any], key: str) -> list[str]:
        raw = cls._unwrap_content_value(content.get(key))
        if isinstance(raw, list):
            out: list[str] = []
            for item in raw:
                text = str(item).strip()
                if text:
                    out.append(text)
            return out
        if isinstance(raw, str):
            text = raw.strip()
            return [text] if text else []
        return []

    @staticmethod
    def _canonical_pdf_url(pdf_value: str, forum_id: str) -> str:
        value = (pdf_value or "").strip()
        if value.startswith("https://") or value.startswith("http://"):
            return value
        if value.startswith("/"):
            return f"https://openreview.net{value}"
        if value:
            return f"https://openreview.net/{value.lstrip('/')}"
        return f"https://openreview.net/pdf?id={forum_id}"

    @classmethod
    def _fields_from_note(cls, note: dict[str, Any]) -> tuple[str, dict[str, str]] | None:
        forum_id = str(note.get("forum") or note.get("id") or "").strip()
        if not forum_id:
            return None
        content = note.get("content")
        if not isinstance(content, dict):
            return None

        title = cls._content_text(content, "title")
        abstract = cls._content_text(content, "abstract")
        pdf = cls._content_text(content, "pdf")
        authors = cls._content_list(content, "authors")
        venue = cls._content_text(content, "venue")

        if not title:
            return None
        if title.lower() in {"paper decision", "decision"} and not abstract and not pdf:
            return None

        source_url = f"https://openreview.net/forum?id={forum_id}"
        fields: dict[str, str] = {
            "url": source_url,
            "pdf": cls._canonical_pdf_url(pdf, forum_id),
            "title": title,
        }
        if abstract:
            fields["abstract"] = abstract
        if authors:
            fields["author"] = " and ".join(authors)
        if venue:
            fields["booktitle"] = venue

        return forum_id, fields

    @staticmethod
    def _bulk_api_base(api_variant: str) -> str:
        if api_variant == "api2":
            return "https://api2.openreview.net/notes"
        return "https://api.openreview.net/notes"

    def _fetch_bulk_notes_page(
        self,
        api_variant: str,
        invitation: str,
        offset: int,
    ) -> tuple[list[dict[str, Any]], str]:
        query = urlencode(
            {
                "invitation": invitation,
                "limit": _OPENREVIEW_API_PAGE_LIMIT,
                "offset": max(0, offset),
            }
        )
        url = f"{self._bulk_api_base(api_variant)}?{query}"
        response = self.http_client.get_text(url, require_any=("notes",))
        if response.status_code != 200:
            return [], response.fetched_at or now_iso()
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            return [], response.fetched_at or now_iso()
        notes = payload.get("notes")
        if not isinstance(notes, list):
            return [], response.fetched_at or now_iso()
        normalized: list[dict[str, Any]] = []
        for row in notes:
            if isinstance(row, dict):
                normalized.append(row)
        return normalized, response.fetched_at or now_iso()

    def _build_bulk_index_for_file(self, file_path: Path) -> dict[str, SourceRecord]:
        file_key = str(file_path)
        if file_key in self._bulk_records_by_file:
            return self._bulk_records_by_file[file_key]
        if file_key in self._bulk_attempted_files:
            return {}
        self._bulk_attempted_files.add(file_key)

        year = self._year_from_file_path(file_path)
        if not year:
            self._bulk_records_by_file[file_key] = {}
            return {}

        records: dict[str, SourceRecord] = {}
        for api_variant, pattern in _OPENREVIEW_BULK_INVITATION_PATTERNS:
            invitation = pattern.format(year=year)
            offset = 0
            while True:
                notes, fetched_at = self._fetch_bulk_notes_page(api_variant, invitation, offset)
                if not notes:
                    break
                for note in notes:
                    payload = self._fields_from_note(note)
                    if payload is None:
                        continue
                    forum_id, fields = payload
                    source_url = f"https://openreview.net/forum?id={forum_id}"
                    candidate = SourceRecord(
                        adapter=self.name,
                        source_url=source_url,
                        fetched_at=fetched_at,
                        fields=fields,
                    )
                    existing = records.get(forum_id)
                    if existing is None:
                        records[forum_id] = candidate
                        continue
                    # Prefer richer rows when multiple invitations emit the same forum.
                    if "abstract" in candidate.fields and "abstract" not in existing.fields:
                        records[forum_id] = candidate
                if len(notes) < _OPENREVIEW_API_PAGE_LIMIT:
                    break
                offset += len(notes)

        self._bulk_records_by_file[file_key] = records
        title_index: dict[str, SourceRecord | None] = {}
        for record in records.values():
            title = normalize_text(record.fields.get("title", ""))
            if not title:
                continue
            existing = title_index.get(title)
            if existing is None and title in title_index:
                continue
            if existing is None:
                title_index[title] = record
                continue
            if existing.source_url != record.source_url:
                title_index[title] = None
        self._bulk_title_index_by_file[file_key] = title_index
        return records

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        file_key = str(context.file_path)
        self._build_bulk_index_for_file(context.file_path)
        forum_id = self._forum_id_from_entry(context.entry)
        if forum_id:
            bulk_records = self._bulk_records_by_file.get(file_key, {})
            bulk_record = bulk_records.get(forum_id)
            if bulk_record is not None:
                return bulk_record
        else:
            title_key = normalize_text(str(context.entry.get("title", "")))
            if title_key:
                title_record = self._bulk_title_index_by_file.get(file_key, {}).get(title_key)
                if title_record is not None:
                    return title_record
            return None

        source_url = f"https://openreview.net/forum?id={forum_id}"
        response = self.http_client.get_text(
            source_url,
            require_any=_OPENREVIEW_REQUIRED_MARKERS,
            reject_any=_OPENREVIEW_REJECT_MARKERS,
        )
        if response.status_code != 200:
            return None

        title = self._meta_value(response.text, "citation_title")
        if not title:
            return None
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

        record = SourceRecord(
            adapter=self.name,
            source_url=source_url,
            fetched_at=response.fetched_at or now_iso(),
            fields=fields,
        )
        # Populate the per-file in-memory index with successful fallback rows.
        if file_key in self._bulk_records_by_file:
            self._bulk_records_by_file[file_key][forum_id] = record
            title = normalize_text(fields.get("title", ""))
            if title:
                title_index = self._bulk_title_index_by_file.setdefault(file_key, {})
                existing = title_index.get(title)
                if existing is None and title in title_index:
                    pass
                elif existing is None or existing.source_url == record.source_url:
                    title_index[title] = record
                else:
                    title_index[title] = None
        return record
