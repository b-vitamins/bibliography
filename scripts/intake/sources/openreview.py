from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from core.http_client import CachedHttpClient
from core.time_utils import now_iso

from ..models import CatalogSnapshot, IntakeRecord
from .base import CatalogContext

_OPENREVIEW_API_PAGE_LIMIT = 1000


class OpenReviewConferenceCatalogAdapter:
    name = "openreview_conference"

    def __init__(self, http_client: CachedHttpClient):
        self.http_client = http_client

    @staticmethod
    def _unwrap_value(value: Any) -> Any:
        if isinstance(value, dict) and "value" in value:
            return value.get("value")
        return value

    @classmethod
    def _content_text(cls, content: dict[str, Any], key: str) -> str:
        raw = cls._unwrap_value(content.get(key))
        if isinstance(raw, str):
            return html.unescape(raw).strip()
        return ""

    @classmethod
    def _content_list(cls, content: dict[str, Any], key: str) -> list[str]:
        raw = cls._unwrap_value(content.get(key))
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
            host = urlparse(value).netloc.lower()
            if host == "openreview.net" or host.endswith(".openreview.net"):
                return value
            return f"https://openreview.net/pdf?id={forum_id}"
        if value.startswith("/"):
            return f"https://openreview.net{value}"
        if value:
            return f"https://openreview.net/{value.lstrip('/')}"
        return f"https://openreview.net/pdf?id={forum_id}"

    @staticmethod
    def _build_invitations(prefix: str, year: int, track: str) -> tuple[tuple[str, str], ...]:
        left = f"{prefix}/{year}/{track}"
        lowered = left.replace("/Conference", "/conference").replace("/Workshop", "/workshop")
        return (
            ("api2", f"{left}/-/Submission"),
            ("api2", f"{left}/-/Post_Submission"),
            ("api2", f"{left}/-/Blind_Submission"),
            ("api1", f"{left}/-/Submission"),
            ("api1", f"{left}/-/Blind_Submission"),
            ("api1", f"{left}/-/Post_Submission"),
            ("api1", f"{lowered}/-/submission"),
            ("api1", f"{lowered}/-/blind_submission"),
        )

    @staticmethod
    def _api_base(api_variant: str) -> str:
        if api_variant == "api2":
            return "https://api2.openreview.net/notes"
        return "https://api.openreview.net/notes"

    def _fetch_notes_page(self, api_variant: str, invitation: str, offset: int) -> tuple[list[dict[str, Any]], str]:
        query = urlencode(
            {
                "invitation": invitation,
                "limit": _OPENREVIEW_API_PAGE_LIMIT,
                "offset": max(0, offset),
            }
        )
        url = f"{self._api_base(api_variant)}?{query}"
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
        out: list[dict[str, Any]] = []
        for row in notes:
            if isinstance(row, dict):
                out.append(row)
        return out, response.fetched_at or now_iso()

    @staticmethod
    def _is_accepted(venue_text: str, year: int, require_venue: bool) -> bool:
        venue = venue_text.strip()
        if not venue:
            return not require_venue
        lowered = venue.lower()
        if lowered.startswith("submitted to"):
            return False
        if "withdrawn" in lowered:
            return False
        if "rejected" in lowered:
            return False
        if str(year) not in lowered and require_venue:
            return False
        return True

    @staticmethod
    def _source_id_from_url(url: str) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in {"openreview.net", "www.openreview.net"}:
            return None
        query = parse_qs(parsed.query)
        ids = query.get("id", [])
        if not ids:
            return None
        return ids[0].strip() or None

    def fetch_catalog(self, context: CatalogContext) -> CatalogSnapshot | None:
        target = context.target
        max_records = max(0, int(context.max_records))
        params = target.params
        prefix = str(params.get("conference_prefix", "")).strip() or f"{target.venue.upper()}.cc"
        track = str(params.get("conference_track", "Conference")).strip() or "Conference"
        booktitle = str(params.get("booktitle", "")).strip() or target.venue.upper()
        publisher = str(params.get("publisher", "")).strip() or "OpenReview.net"
        require_venue = bool(params.get("require_venue", True))

        invitations = self._build_invitations(prefix, target.year, track)
        records: dict[str, IntakeRecord] = {}
        notes_seen = 0
        invitations_hit = 0
        last_fetched_at = now_iso()

        for api_variant, invitation in invitations:
            offset = 0
            hit_this_invitation = False
            while True:
                notes, fetched_at = self._fetch_notes_page(api_variant, invitation, offset)
                last_fetched_at = fetched_at
                if not notes:
                    break
                hit_this_invitation = True
                notes_seen += len(notes)
                for note in notes:
                    content = note.get("content")
                    if not isinstance(content, dict):
                        continue
                    forum_id = str(note.get("forum") or note.get("id") or "").strip()
                    if not forum_id:
                        continue

                    title = self._content_text(content, "title")
                    authors = self._content_list(content, "authors")
                    abstract = self._content_text(content, "abstract")
                    pdf = self._content_text(content, "pdf")
                    doi = self._content_text(content, "doi")
                    venue_text = self._content_text(content, "venue")

                    if not title or not authors:
                        continue
                    if title.lower() in {"paper decision", "decision"}:
                        continue
                    if not self._is_accepted(venue_text, target.year, require_venue):
                        continue

                    source_url = f"https://openreview.net/forum?id={forum_id}"
                    candidate = IntakeRecord(
                        source_id=forum_id,
                        source_url=source_url,
                        title=title,
                        authors=authors,
                        year=target.year,
                        booktitle=booktitle,
                        publisher=publisher,
                        url=source_url,
                        pdf=self._canonical_pdf_url(pdf, forum_id),
                        abstract=abstract or None,
                        doi=doi or None,
                        extra_fields={"source_adapter": self.name},
                    )
                    existing = records.get(forum_id)
                    if existing is None:
                        records[forum_id] = candidate
                    else:
                        # Prefer richer rows when repeated across invitations.
                        if (not existing.abstract) and candidate.abstract:
                            records[forum_id] = candidate
                    if max_records and len(records) >= max_records:
                        break

                if len(notes) < _OPENREVIEW_API_PAGE_LIMIT:
                    break
                if max_records and len(records) >= max_records:
                    break
                offset += len(notes)

            if max_records and len(records) >= max_records:
                invitations_hit += 1 if hit_this_invitation else 0
                break
            if hit_this_invitation:
                invitations_hit += 1

        if not records:
            return None

        return CatalogSnapshot(
            adapter=self.name,
            target=target,
            fetched_at=last_fetched_at,
            records=sorted(records.values(), key=lambda r: (r.title.lower(), r.source_id)),
            expected_count=len(records),
            metadata={
                "conference_prefix": prefix,
                "conference_track": track,
                "invitations_tried": [inv for _api, inv in invitations],
                "invitations_hit": invitations_hit,
                "notes_seen": notes_seen,
                "require_venue": require_venue,
            },
        )

    def source_id_from_entry(self, entry: dict[str, Any]) -> str | None:
        sourceid = str(entry.get("sourceid", "")).strip()
        if sourceid.lower().startswith(f"{self.name}:"):
            suffix = sourceid.split(":", 1)[1].strip()
            if suffix:
                return suffix
        for field in ("url", "pdf"):
            found = self._source_id_from_url(str(entry.get(field, "")).strip())
            if found:
                return found
        return None

    def supports(self, file_path) -> bool:
        path = str(file_path).lower()
        return "/conferences/" in path or path.startswith("conferences/")
