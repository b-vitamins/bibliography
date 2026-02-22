from __future__ import annotations

import dataclasses
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from ..normalization import normalize_spaces, normalize_text, strip_latex
from .base import AdapterContext

_S2_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
_S2_PAPER_MATCH_URL = f"{_S2_PAPER_URL}/search/match"
_S2_PAPER_REQUIRED_MARKERS = ('"paperId"',)
_S2_MATCH_REQUIRED_MARKERS = ('"data"',)
_MAX_QUERY_CHARS = 256
_CONF_TYPES = {"inproceedings", "incollection", "proceedings"}
_JOURNAL_TYPES = {"article"}
_MONTH_BY_NUMBER = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dec",
}


@dataclasses.dataclass
class _LookupResult:
    payload: dict[str, Any]
    source_url: str
    fetched_at: str


class SemanticScholarAdapter:
    name = "semanticscholar"
    provided_fields = {
        "author",
        "abstract",
        "doi",
        "note",
        "year",
        "month",
        "booktitle",
        "journal",
        "volume",
        "number",
        "pages",
        "keywords",
        "url",
        "pdf",
    }

    _fields_param = ",".join(
        [
            "paperId",
            "externalIds",
            "title",
            "year",
            "publicationDate",
            "venue",
            "publicationVenue",
            "journal",
            "authors",
            "abstract",
            "url",
            "openAccessPdf",
            "fieldsOfStudy",
            "tldr",
        ]
    )

    def __init__(
        self,
        http_client: CachedHttpClient,
        min_title_score: float = 0.94,
        min_confidence: float = 0.91,
        api_key: str = "",
    ) -> None:
        self.http_client = http_client
        self.min_title_score = max(0.0, min(1.0, float(min_title_score)))
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.api_key = api_key.strip()
        self._id_cache: dict[str, _LookupResult | None] = {}
        self._title_cache: dict[str, _LookupResult | None] = {}

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        entry_type = str(entry.get("ENTRYTYPE", "")).strip().lower()
        if entry_type not in {
            "inproceedings",
            "article",
            "misc",
            "unpublished",
            "techreport",
            "incollection",
            "book",
            "phdthesis",
            "mastersthesis",
        }:
            return False
        title = str(entry.get("title", "")).strip()
        if title:
            return True
        return bool(self._entry_identifier_candidates(entry))

    def _request_headers(self) -> dict[str, str] | None:
        if not self.api_key:
            return None
        return {"x-api-key": self.api_key}

    @staticmethod
    def _ascii_text(value: str) -> str:
        return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")

    @classmethod
    def _tokenize_title(cls, value: str) -> set[str]:
        return {token for token in normalize_text(value).split(" ") if token}

    @classmethod
    def _title_similarity(cls, left: str, right: str) -> float:
        a = normalize_text(left)
        b = normalize_text(right)
        if not a or not b:
            return 0.0
        seq = SequenceMatcher(a=a, b=b).ratio()
        ta = cls._tokenize_title(a)
        tb = cls._tokenize_title(b)
        if not ta or not tb:
            return seq
        jac = len(ta & tb) / len(ta | tb)
        return max(seq, 0.7 * seq + 0.3 * jac)

    @staticmethod
    def _parse_year(value: Any) -> int | None:
        if value is None:
            return None
        match = re.search(r"(19|20)\d{2}", str(value).strip())
        if not match:
            return None
        return int(match.group(0))

    @classmethod
    def _parse_authors(cls, value: str) -> list[str]:
        if not value:
            return []
        parts = [part.strip() for part in value.split(" and ") if part.strip()]
        return [normalize_spaces(strip_latex(part)) for part in parts]

    @classmethod
    def _surname(cls, value: str) -> str:
        text = cls._ascii_text(value).lower().strip()
        if not text:
            return ""
        if "," in text:
            left = text.split(",", 1)[0].strip()
            tokens = re.findall(r"[a-z0-9]+", left)
            return tokens[-1] if tokens else ""
        tokens = re.findall(r"[a-z0-9]+", text)
        return tokens[-1] if tokens else ""

    @classmethod
    def _entry_first_author_surname(cls, entry: dict[str, Any]) -> str:
        raw_author = str(entry.get("author", "")).strip()
        if cls._is_placeholder_author(raw_author):
            return ""
        authors = cls._parse_authors(str(entry.get("author", "")))
        if not authors:
            return ""
        return cls._surname(authors[0])

    @staticmethod
    def _normalize_doi(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        prefixes = (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                text = text[len(prefix) :].strip()
                lowered = text.lower()
                break
        text = text.replace(" ", "")
        return text

    @staticmethod
    def _extract_arxiv_id(value: str) -> str:
        text = value or ""
        if not text:
            return ""
        match = re.search(
            r"arxiv\.org/(?:abs|pdf)/([A-Za-z\-\.]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?",
            text,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"arXiv:([A-Za-z\-\.]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?",
                text,
                re.IGNORECASE,
            )
        if not match:
            match = re.search(
                r"\b([A-Za-z\-\.]+/[0-9]{7}|[0-9]{4}\.[0-9]{4,5})(?:v\d+)?\b",
                text,
            )
            if not match:
                return ""
        return match.group(1)

    @staticmethod
    def _entry_s2_paper_id(entry: dict[str, Any]) -> str:
        url = str(entry.get("url", "")).strip()
        if not url:
            return ""
        match = re.search(r"/paper/(?:[^/]+/)?([0-9a-f]{40})(?:[/?#]|$)", url, flags=re.I)
        if not match:
            return ""
        return match.group(1)

    @classmethod
    def _entry_identifier_candidates(cls, entry: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            token = candidate.strip()
            if not token or token in seen:
                return
            seen.add(token)
            candidates.append(token)

        s2_id = cls._entry_s2_paper_id(entry)
        if s2_id:
            add(s2_id)

        doi = cls._normalize_doi(str(entry.get("doi", "")))
        if doi:
            add(f"DOI:{doi}")

        arxiv_id = cls._extract_arxiv_id(str(entry.get("arxiv", "")))
        if not arxiv_id:
            archive_prefix = str(entry.get("archiveprefix", "")).strip().lower()
            eprint = str(entry.get("eprint", "")).strip()
            if archive_prefix == "arxiv" and eprint:
                arxiv_id = cls._extract_arxiv_id(eprint) or eprint
        if not arxiv_id:
            for field in ("url", "pdf"):
                arxiv_id = cls._extract_arxiv_id(str(entry.get(field, "")))
                if arxiv_id:
                    break
        if arxiv_id:
            add(f"ARXIV:{arxiv_id}")

        return candidates

    @staticmethod
    def _candidate_year_score(entry_year: int | None, candidate_year: int | None) -> float:
        if entry_year is None or candidate_year is None:
            return 0.5
        delta = abs(entry_year - candidate_year)
        if delta == 0:
            return 1.0
        if delta == 1:
            return 0.95
        if delta == 2:
            return 0.6
        return 0.1

    @classmethod
    def _candidate_author_score(cls, first_surname: str, candidate_authors: list[str]) -> float:
        if not first_surname:
            return 0.5
        if not candidate_authors:
            return 0.4
        candidate_surnames = {cls._surname(author) for author in candidate_authors if cls._surname(author)}
        if first_surname in candidate_surnames:
            return 1.0
        return 0.0

    @classmethod
    def _candidate_authors(cls, payload: dict[str, Any]) -> list[str]:
        rows = payload.get("authors")
        if not isinstance(rows, list):
            return []
        out: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = normalize_spaces(str(row.get("name", "")).strip())
            if name:
                out.append(name)
        return out

    def _match_scores(self, entry: dict[str, Any], payload: dict[str, Any]) -> tuple[float, float]:
        entry_title = str(entry.get("title", "")).strip()
        candidate_title = str(payload.get("title", "")).strip()
        if not entry_title:
            return 1.0, 1.0

        title_score = self._title_similarity(entry_title, candidate_title)
        author_score = self._candidate_author_score(
            self._entry_first_author_surname(entry),
            self._candidate_authors(payload),
        )
        year_score = self._candidate_year_score(
            self._parse_year(entry.get("year")),
            self._parse_year(payload.get("year")),
        )
        confidence = 0.72 * title_score + 0.18 * author_score + 0.10 * year_score
        return title_score, confidence

    def _is_payload_match(
        self,
        entry: dict[str, Any],
        payload: dict[str, Any],
        min_title_score: float,
        min_confidence: float,
    ) -> bool:
        epsilon = 1e-9
        if not str(payload.get("paperId", "")).strip():
            return False
        entry_title = str(entry.get("title", "")).strip()
        if not entry_title:
            return True
        title_score, confidence = self._match_scores(entry, payload)
        if title_score + epsilon < min_title_score:
            return False
        if confidence + epsilon < min_confidence:
            return False
        return True

    @staticmethod
    def _payload_source_url(payload: dict[str, Any], fallback: str) -> str:
        value = str(payload.get("url", "")).strip()
        if value:
            return value
        return fallback

    def _query_paper_by_id(self, paper_id: str) -> _LookupResult | None:
        cache_key = paper_id.strip()
        if cache_key in self._id_cache:
            return self._id_cache[cache_key]

        encoded_id = quote(cache_key, safe="")
        url = f"{_S2_PAPER_URL}/{encoded_id}?{urlencode({'fields': self._fields_param})}"
        response = self.http_client.get_text(
            url,
            headers=self._request_headers(),
            require_any=_S2_PAPER_REQUIRED_MARKERS,
        )
        if response.status_code != 200:
            self._id_cache[cache_key] = None
            return None
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            self._id_cache[cache_key] = None
            return None
        if not isinstance(payload, dict):
            self._id_cache[cache_key] = None
            return None
        if not str(payload.get("paperId", "")).strip():
            self._id_cache[cache_key] = None
            return None
        result = _LookupResult(
            payload=payload,
            source_url=self._payload_source_url(payload, url),
            fetched_at=response.fetched_at or now_iso(),
        )
        self._id_cache[cache_key] = result
        return result

    def _query_title_match(self, entry: dict[str, Any]) -> _LookupResult | None:
        title = str(entry.get("title", "")).strip()
        if not title:
            return None
        year = self._parse_year(entry.get("year"))
        cache_key = f"{normalize_text(title)}|{year or ''}"
        if cache_key in self._title_cache:
            return self._title_cache[cache_key]

        params: dict[str, str] = {
            "query": title[:_MAX_QUERY_CHARS],
            "fields": self._fields_param,
        }
        if year is not None:
            params["year"] = f"{max(1800, year - 1)}-{year + 1}"
        url = f"{_S2_PAPER_MATCH_URL}?{urlencode(params)}"
        response = self.http_client.get_text(
            url,
            headers=self._request_headers(),
            require_any=_S2_MATCH_REQUIRED_MARKERS,
        )
        if response.status_code not in {200, 404}:
            self._title_cache[cache_key] = None
            return None
        if response.status_code == 404:
            self._title_cache[cache_key] = None
            return None
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            self._title_cache[cache_key] = None
            return None
        rows = payload.get("data")
        if not isinstance(rows, list) or not rows:
            self._title_cache[cache_key] = None
            return None
        first = rows[0]
        if not isinstance(first, dict):
            self._title_cache[cache_key] = None
            return None
        if not str(first.get("paperId", "")).strip():
            self._title_cache[cache_key] = None
            return None
        result = _LookupResult(
            payload=first,
            source_url=self._payload_source_url(first, url),
            fetched_at=response.fetched_at or now_iso(),
        )
        self._title_cache[cache_key] = result
        return result

    @staticmethod
    def _is_placeholder_author(value: str) -> bool:
        normalized = normalize_text(value)
        if not normalized:
            return False
        if normalized in {"others", "and others", "et al", "et al."}:
            return True
        if " and others" in normalized:
            return True
        if normalized.endswith(" et al") or normalized.endswith(" et al."):
            return True
        return False

    @classmethod
    def _extract_doi(cls, payload: dict[str, Any]) -> str:
        external = payload.get("externalIds")
        if not isinstance(external, dict):
            return ""
        for key, value in external.items():
            if str(key).strip().lower() != "doi":
                continue
            doi = cls._normalize_doi(str(value))
            if doi:
                return doi
        return ""

    @staticmethod
    def _extract_tldr(payload: dict[str, Any]) -> str:
        row = payload.get("tldr")
        if not isinstance(row, dict):
            return ""
        text = normalize_spaces(str(row.get("text", "")).strip())
        return text

    @staticmethod
    def _extract_publication_venue(payload: dict[str, Any]) -> str:
        publication_venue = payload.get("publicationVenue")
        if isinstance(publication_venue, dict):
            name = normalize_spaces(str(publication_venue.get("name", "")).strip())
            if name:
                return name
        venue = normalize_spaces(str(payload.get("venue", "")).strip())
        return venue

    @staticmethod
    def _extract_publication_date(payload: dict[str, Any]) -> tuple[str, str]:
        value = str(payload.get("publicationDate", "")).strip()
        if not value:
            return "", ""
        parts = value.split("-")
        if len(parts) < 2:
            return "", ""
        try:
            month = int(parts[1])
        except Exception:
            month = 0
        month_value = _MONTH_BY_NUMBER.get(month, "")
        return value, month_value

    @staticmethod
    def _extract_journal_fields(payload: dict[str, Any]) -> tuple[str, str, str, str]:
        row = payload.get("journal")
        if not isinstance(row, dict):
            return "", "", "", ""
        name = normalize_spaces(str(row.get("name", "")).strip())
        volume = normalize_spaces(str(row.get("volume", "")).strip())
        number = normalize_spaces(str(row.get("issue", "")).strip())
        pages = normalize_spaces(str(row.get("pages", "")).strip())
        return name, volume, number, pages

    @staticmethod
    def _extract_keywords(payload: dict[str, Any]) -> str:
        rows = payload.get("fieldsOfStudy")
        if not isinstance(rows, list):
            return ""
        seen: set[str] = set()
        out: list[str] = []
        for row in rows:
            value = normalize_spaces(str(row).strip())
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return ", ".join(out)

    @staticmethod
    def _extract_pdf(payload: dict[str, Any]) -> str:
        row = payload.get("openAccessPdf")
        if not isinstance(row, dict):
            return ""
        value = normalize_spaces(str(row.get("url", "")).strip())
        return value

    def _source_fields_from_payload(self, payload: dict[str, Any], entry: dict[str, Any]) -> dict[str, str]:
        fields: dict[str, str] = {}
        entry_type = str(entry.get("ENTRYTYPE", "")).strip().lower()

        authors = self._candidate_authors(payload)
        current_author = str(entry.get("author", "")).strip()
        if authors and (not current_author or self._is_placeholder_author(current_author)):
            fields["author"] = " and ".join(authors)

        doi = self._extract_doi(payload)
        if doi:
            fields["doi"] = doi

        abstract = normalize_spaces(str(payload.get("abstract", "")).strip())
        if abstract and not str(entry.get("abstract", "")).strip():
            fields["abstract"] = abstract

        tldr = self._extract_tldr(payload)
        if tldr and not str(entry.get("note", "")).strip():
            fields["note"] = f"TL;DR: {tldr}"

        year = self._parse_year(payload.get("year"))
        if year is not None and not str(entry.get("year", "")).strip():
            fields["year"] = str(year)

        _publication_date, month = self._extract_publication_date(payload)
        if month and not str(entry.get("month", "")).strip():
            fields["month"] = month

        venue = self._extract_publication_venue(payload)
        if venue and entry_type in _CONF_TYPES and not str(entry.get("booktitle", "")).strip():
            fields["booktitle"] = venue

        journal_name, volume, number, pages = self._extract_journal_fields(payload)
        if entry_type in _JOURNAL_TYPES:
            if journal_name and not str(entry.get("journal", "")).strip():
                fields["journal"] = journal_name
            if volume and not str(entry.get("volume", "")).strip():
                fields["volume"] = volume
            if number and not str(entry.get("number", "")).strip():
                fields["number"] = number
            if pages and not str(entry.get("pages", "")).strip():
                fields["pages"] = pages

        keywords = self._extract_keywords(payload)
        if keywords and not str(entry.get("keywords", "")).strip():
            fields["keywords"] = keywords

        source_url = normalize_spaces(str(payload.get("url", "")).strip())
        if source_url and not str(entry.get("url", "")).strip():
            fields["url"] = source_url

        pdf_url = self._extract_pdf(payload)
        if pdf_url and not str(entry.get("pdf", "")).strip():
            fields["pdf"] = pdf_url

        return fields

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        lookup: _LookupResult | None = None

        # Prefer high-confidence identifier lookups when DOI/arXiv IDs exist.
        for candidate_id in self._entry_identifier_candidates(context.entry):
            result = self._query_paper_by_id(candidate_id)
            if result is None:
                continue
            if self._is_payload_match(
                context.entry,
                result.payload,
                min_title_score=0.82,
                min_confidence=0.75,
            ):
                lookup = result
                break

        if lookup is None:
            result = self._query_title_match(context.entry)
            if result is None:
                return None
            if not self._is_payload_match(
                context.entry,
                result.payload,
                min_title_score=self.min_title_score,
                min_confidence=self.min_confidence,
            ):
                return None
            lookup = result

        fields = self._source_fields_from_payload(lookup.payload, context.entry)
        return SourceRecord(
            adapter=self.name,
            source_url=lookup.source_url,
            fetched_at=lookup.fetched_at or now_iso(),
            fields=fields,
        )
