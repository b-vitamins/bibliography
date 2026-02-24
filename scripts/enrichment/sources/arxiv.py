from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from ..http_client import CachedHttpClient
from ..models import SourceRecord, now_iso
from ..normalization import normalize_text, normalize_spaces, strip_latex
from .base import AdapterContext

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_API_URL = "https://export.arxiv.org/api/query"

_MAX_TITLE_QUERY_CHARS = 256
_OPENALEX_REQUIRED_MARKERS = ('"results"',)
_ARXIV_REQUIRED_MARKERS = ("<feed", "<entry")


@dataclasses.dataclass
class _Candidate:
    arxiv_id: str
    abs_url: str
    title: str
    authors: list[str]
    year: int | None
    primary_class: str | None
    source: str
    source_rank: int


@dataclasses.dataclass
class _Match:
    candidate: _Candidate
    title_score: float
    author_score: float
    year_score: float
    confidence: float


class ArxivAdapter:
    name = "arxiv"
    provided_fields = {"eprint", "archiveprefix", "primaryclass", "arxiv"}

    def __init__(
        self,
        http_client: CachedHttpClient,
        min_title_score: float = 0.92,
        min_confidence: float = 0.90,
        enable_openalex: bool = True,
        openalex_max_results: int = 15,
        arxiv_max_results: int = 12,
        openalex_mailto: str = "",
        openalex_api_key: str = "",
    ) -> None:
        self.http_client = http_client
        self.min_title_score = max(0.0, min(1.0, float(min_title_score)))
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.enable_openalex = bool(enable_openalex)
        self.openalex_max_results = max(1, min(100, int(openalex_max_results)))
        self.arxiv_max_results = max(1, min(100, int(arxiv_max_results)))
        self.openalex_mailto = openalex_mailto.strip()
        self.openalex_api_key = openalex_api_key.strip()
        self._openalex_query_cache: dict[str, list[_Candidate]] = {}
        self._arxiv_query_cache: dict[str, list[_Candidate]] = {}

    def supports(self, file_path: Path, entry: dict[str, Any]) -> bool:
        if not str(entry.get("title", "")).strip():
            return False
        if self._has_arxiv_fields(entry):
            return False
        entry_type = str(entry.get("ENTRYTYPE", "")).strip().lower()
        return entry_type in {
            "inproceedings",
            "article",
            "misc",
            "unpublished",
            "techreport",
            "incollection",
            "book",
            "phdthesis",
            "mastersthesis",
        }

    @staticmethod
    def _has_arxiv_fields(entry: dict[str, Any]) -> bool:
        eprint = str(entry.get("eprint", "")).strip()
        archiveprefix = str(entry.get("archiveprefix", "")).strip().lower()
        arxiv = str(entry.get("arxiv", "")).strip().lower()
        if eprint and archiveprefix == "arxiv":
            return True
        if arxiv and "arxiv.org/abs/" in arxiv:
            return True
        return False

    @staticmethod
    def _ascii_text(value: str) -> str:
        return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")

    @classmethod
    def _normalize_title(cls, value: str) -> str:
        return normalize_text(value)

    @classmethod
    def _tokenize_title(cls, value: str) -> set[str]:
        return {token for token in cls._normalize_title(value).split(" ") if token}

    @classmethod
    def _title_similarity(cls, left: str, right: str) -> float:
        a = cls._normalize_title(left)
        b = cls._normalize_title(right)
        if not a or not b:
            return 0.0
        seq = SequenceMatcher(a=a, b=b).ratio()
        ta = cls._tokenize_title(a)
        tb = cls._tokenize_title(b)
        if not ta or not tb:
            return seq
        jac = len(ta & tb) / len(ta | tb)
        return max(seq, 0.65 * seq + 0.35 * jac)

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
        authors = cls._parse_authors(str(entry.get("author", "")))
        if not authors:
            return ""
        return cls._surname(authors[0])

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

    @classmethod
    def _candidate_from_openalex(cls, row: dict[str, Any], rank: int) -> _Candidate | None:
        ids = row.get("ids") if isinstance(row.get("ids"), dict) else {}
        arxiv_id = cls._extract_arxiv_id(str(ids.get("arxiv", "") if ids else ""))
        if not arxiv_id:
            for loc in row.get("locations") or []:
                if not isinstance(loc, dict):
                    continue
                for field in ("landing_page_url", "pdf_url"):
                    arxiv_id = cls._extract_arxiv_id(str(loc.get(field, "")))
                    if arxiv_id:
                        break
                if arxiv_id:
                    break
        if not arxiv_id:
            return None

        title = str(row.get("title") or row.get("display_name") or "").strip()
        year = cls._parse_year(row.get("publication_year"))
        authors = [
            str(((auth or {}).get("author") or {}).get("display_name") or "").strip()
            for auth in (row.get("authorships") or [])
            if ((auth or {}).get("author") or {}).get("display_name")
        ]
        return _Candidate(
            arxiv_id=arxiv_id,
            abs_url=f"https://arxiv.org/abs/{arxiv_id}",
            title=title,
            authors=authors,
            year=year,
            primary_class=None,
            source="openalex",
            source_rank=rank,
        )

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
    def _compute_match(cls, entry: dict[str, Any], candidate: _Candidate) -> _Match:
        title_score = cls._title_similarity(str(entry.get("title", "")), candidate.title)
        author_score = cls._candidate_author_score(
            cls._entry_first_author_surname(entry),
            candidate.authors,
        )
        year_score = cls._candidate_year_score(
            cls._parse_year(entry.get("year")),
            candidate.year,
        )
        confidence = 0.72 * title_score + 0.18 * author_score + 0.10 * year_score
        if candidate.source == "openalex":
            confidence = min(1.0, confidence + 0.03)
        return _Match(
            candidate=candidate,
            title_score=title_score,
            author_score=author_score,
            year_score=year_score,
            confidence=confidence,
        )

    def _pick_best_match(self, entry: dict[str, Any], candidates: list[_Candidate]) -> _Match | None:
        if not candidates:
            return None
        ranked = sorted(
            (self._compute_match(entry, candidate) for candidate in candidates),
            key=lambda match: (
                match.confidence,
                match.title_score,
                -match.candidate.source_rank,
            ),
            reverse=True,
        )
        top = ranked[0]
        if top.title_score < self.min_title_score:
            return None
        if top.confidence < self.min_confidence:
            return None
        return top

    def _query_openalex(self, title: str) -> list[_Candidate]:
        norm_key = hashlib.sha1(self._normalize_title(title).encode("utf-8")).hexdigest()
        cached = self._openalex_query_cache.get(norm_key)
        if cached is not None:
            return cached

        params: dict[str, str | int] = {
            "search": title[:_MAX_TITLE_QUERY_CHARS],
            "per-page": self.openalex_max_results,
        }
        if self.openalex_mailto:
            params["mailto"] = self.openalex_mailto
        if self.openalex_api_key:
            params["api_key"] = self.openalex_api_key
        url = f"{OPENALEX_WORKS_URL}?{urlencode(params)}"
        response = self.http_client.get_text(
            url,
            require_any=_OPENALEX_REQUIRED_MARKERS,
        )
        if response.status_code != 200:
            self._openalex_query_cache[norm_key] = []
            return []

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            self._openalex_query_cache[norm_key] = []
            return []

        candidates: list[_Candidate] = []
        for rank, row in enumerate(payload.get("results") or []):
            if not isinstance(row, dict):
                continue
            candidate = self._candidate_from_openalex(row, rank=rank)
            if candidate is not None:
                candidates.append(candidate)

        self._openalex_query_cache[norm_key] = candidates
        return candidates

    @staticmethod
    def _parse_arxiv_feed(xml_text: str) -> list[_Candidate]:
        if not xml_text.strip():
            return []
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return []

        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        candidates: list[_Candidate] = []
        for rank, row in enumerate(root.findall("atom:entry", ns)):
            abs_url = normalize_spaces(row.findtext("atom:id", default="", namespaces=ns))
            arxiv_id = ArxivAdapter._extract_arxiv_id(abs_url)
            if not arxiv_id:
                continue
            title = normalize_spaces(row.findtext("atom:title", default="", namespaces=ns))
            year = ArxivAdapter._parse_year(row.findtext("atom:published", default="", namespaces=ns))
            authors = [
                normalize_spaces(author.findtext("atom:name", default="", namespaces=ns))
                for author in row.findall("atom:author", ns)
            ]
            primary_class = None
            primary = row.find("arxiv:primary_category", ns)
            if primary is not None:
                primary_class = str(primary.attrib.get("term") or "").strip() or None

            candidates.append(
                _Candidate(
                    arxiv_id=arxiv_id,
                    abs_url=f"https://arxiv.org/abs/{arxiv_id}",
                    title=title,
                    authors=authors,
                    year=year,
                    primary_class=primary_class,
                    source="arxiv",
                    source_rank=rank,
                )
            )
        return candidates

    def _query_arxiv(self, title: str, author_surname: str) -> list[_Candidate]:
        cache_key = hashlib.sha1(
            (self._normalize_title(title) + "|" + author_surname).encode("utf-8")
        ).hexdigest()
        cached = self._arxiv_query_cache.get(cache_key)
        if cached is not None:
            return cached

        title_query = title[:_MAX_TITLE_QUERY_CHARS]
        if author_surname:
            query = f'ti:"{title_query}" AND au:{author_surname}'
        else:
            query = f'ti:"{title_query}"'

        params = {
            "search_query": query,
            "start": 0,
            "max_results": self.arxiv_max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API_URL}?{urlencode(params)}"
        response = self.http_client.get_text(
            url,
            require_any=_ARXIV_REQUIRED_MARKERS,
        )
        if response.status_code != 200:
            self._arxiv_query_cache[cache_key] = []
            return []

        candidates = self._parse_arxiv_feed(response.text)
        self._arxiv_query_cache[cache_key] = candidates
        return candidates

    def fetch(self, context: AdapterContext) -> SourceRecord | None:
        title = str(context.entry.get("title", "")).strip()
        if not title:
            return None

        openalex_candidates: list[_Candidate] = []
        if self.enable_openalex:
            openalex_candidates = self._query_openalex(title)
        match = self._pick_best_match(context.entry, openalex_candidates)
        if match is None:
            arxiv_candidates = self._query_arxiv(
                title=title,
                author_surname=self._entry_first_author_surname(context.entry),
            )
            match = self._pick_best_match(
                context.entry,
                openalex_candidates + arxiv_candidates,
            )
        if match is None:
            return None

        fields: dict[str, str] = {
            "eprint": match.candidate.arxiv_id,
            "archiveprefix": "arXiv",
            "arxiv": match.candidate.abs_url,
        }
        if match.candidate.primary_class:
            fields["primaryclass"] = match.candidate.primary_class

        return SourceRecord(
            adapter=self.name,
            source_url=match.candidate.abs_url,
            fetched_at=now_iso(),
            fields=fields,
        )
