from __future__ import annotations

import datetime as dt
import json
import random
import re
import time
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .time_utils import now_iso

_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_RATE_LIMIT_BODY_MARKERS = (
    "too many requests",
    "surpassing the limit of",
    "please try again in",
)
_POISON_BODY_MARKERS = (
    "too many requests:",
    "surpassing the limit of",
    "please try again in",
    "the server responded with the following message",
    "attention required! | cloudflare",
    "cf-chl-",
    "verify you are human",
)
_RETRY_AFTER_BODY_RE = re.compile(
    r"(?:try again in|please wait|retry after)\s+(\d+)\s+seconds",
    flags=re.I,
)


@dataclass
class HttpResponse:
    url: str
    status_code: int
    text: str
    fetched_at: str
    from_cache: bool


class CachedHttpClient:
    def __init__(
        self,
        timeout_seconds: float,
        max_retries: int,
        max_validation_retries: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        user_agent: str,
        cache_path: Path,
        host_min_interval: float = 0.2,
        host_min_interval_by_host: dict[str, float] | None = None,
        host_circuit_breaker_threshold: int = 0,
        host_circuit_breaker_cooldown_seconds: float = 0.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.max_validation_retries = max(0, max_validation_retries)
        self.backoff_base_seconds = max(0.1, backoff_base_seconds)
        self.backoff_max_seconds = max(self.backoff_base_seconds, backoff_max_seconds)
        self.cache_path = cache_path
        self.host_min_interval = max(0.0, host_min_interval)
        self.host_min_interval_by_host = {
            str(host).strip().lower(): max(0.0, float(interval))
            for host, interval in (host_min_interval_by_host or {}).items()
            if str(host).strip()
        }
        self.host_circuit_breaker_threshold = max(0, int(host_circuit_breaker_threshold))
        self.host_circuit_breaker_cooldown_seconds = max(0.0, float(host_circuit_breaker_cooldown_seconds))
        self._cache_dirty = False
        self._stats: dict[str, int | float] = {
            "cache_entries_loaded": 0,
            "cache_entries_purged_on_load": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_writes": 0,
            "cache_invalidated_runtime": 0,
            "network_requests": 0,
            "validation_failures": 0,
            "rate_limit_events": 0,
            "retry_count": 0,
            "retry_sleep_seconds": 0.0,
            "poison_responses_discarded": 0,
            "request_exceptions": 0,
            "circuit_breaker_trips": 0,
            "circuit_breaker_short_circuits": 0,
        }
        self._cache: dict[str, dict[str, str | int]] = {}
        self._load_cache(cache_path)
        self._last_request_by_host: dict[str, float] = {}
        self._host_cooldown_until_by_host: dict[str, float] = {}
        self._host_failure_streak_by_host: dict[str, int] = {}
        self._host_breaker_until_by_host: dict[str, float] = {}

        self.session = requests.Session()
        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            backoff_factor=0.3,
            backoff_max=5,
            status_forcelist=sorted(_RETRYABLE_STATUS_CODES),
            allowed_methods=["GET"],
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent})

    def _host_interval(self, host: str) -> float:
        if not host:
            return self.host_min_interval
        if host in self.host_min_interval_by_host:
            return self.host_min_interval_by_host[host]
        # Support parent-domain rules such as "openreview.net".
        match = 0.0
        best_len = -1
        for domain, interval in self.host_min_interval_by_host.items():
            if host.endswith(f".{domain}") and len(domain) > best_len:
                match = interval
                best_len = len(domain)
        if best_len >= 0:
            return match
        return self.host_min_interval

    @staticmethod
    def _normalize_markers(markers: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        if not markers:
            return ()
        out: list[str] = []
        for marker in markers:
            if not marker:
                continue
            value = marker.strip().lower()
            if value:
                out.append(value)
        return tuple(out)

    @staticmethod
    def _contains_any_marker(text: str, markers: tuple[str, ...]) -> bool:
        if not markers:
            return False
        lowered = (text or "").lower()
        return any(marker in lowered for marker in markers)

    def _is_rate_limited_response(self, status_code: int, text: str) -> bool:
        if status_code == 429:
            return True
        return self._contains_any_marker(text, _RATE_LIMIT_BODY_MARKERS)

    def _is_poisoned_response(self, status_code: int, text: str) -> bool:
        if status_code in {0, 408, 425, 429} or status_code >= 500:
            return True
        return self._contains_any_marker(text, _POISON_BODY_MARKERS)

    def _load_cache(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        responses = data.get("responses")
        if not isinstance(responses, dict):
            return
        purged = 0
        for url, payload in responses.items():
            if not isinstance(url, str) or not isinstance(payload, dict):
                continue
            status_code = int(payload.get("status_code", 0))
            text = str(payload.get("text", ""))
            fetched_at = str(payload.get("fetched_at", ""))
            self._stats["cache_entries_loaded"] = int(self._stats["cache_entries_loaded"]) + 1
            if self._is_poisoned_response(status_code, text):
                purged += 1
                continue
            self._cache[url] = {
                "status_code": status_code,
                "text": text,
                "fetched_at": fetched_at,
            }

        if purged:
            self._cache_dirty = True
        self._stats["cache_entries_purged_on_load"] = purged

    def _save_cache(self) -> None:
        if not self._cache_dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "responses": self._cache}
        self.cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._cache_dirty = False

    def _respect_host_interval(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if not host:
            return
        host_min_interval = self._host_interval(host)
        now = time.monotonic()
        target = self._host_cooldown_until_by_host.get(host, 0.0)
        last = self._last_request_by_host.get(host)
        if last is not None:
            target = max(target, last + host_min_interval)
        if now < target:
            time.sleep(target - now)
        self._last_request_by_host[host] = time.monotonic()

    def _set_host_cooldown(self, url: str, delay_seconds: float) -> None:
        host = urlparse(url).netloc.lower()
        if not host:
            return
        until = time.monotonic() + max(0.0, delay_seconds)
        existing = self._host_cooldown_until_by_host.get(host, 0.0)
        self._host_cooldown_until_by_host[host] = max(existing, until)

    def _record_host_success(self, host: str) -> None:
        if not host:
            return
        self._host_failure_streak_by_host[host] = 0

    def _record_host_transient_failure(self, host: str) -> None:
        if not host:
            return
        streak = self._host_failure_streak_by_host.get(host, 0) + 1
        self._host_failure_streak_by_host[host] = streak
        if self.host_circuit_breaker_threshold <= 0:
            return
        if streak < self.host_circuit_breaker_threshold:
            return
        if self.host_circuit_breaker_cooldown_seconds <= 0:
            return
        until = time.monotonic() + self.host_circuit_breaker_cooldown_seconds
        existing = self._host_breaker_until_by_host.get(host, 0.0)
        if until > existing:
            self._host_breaker_until_by_host[host] = until
            self._stats["circuit_breaker_trips"] = int(self._stats["circuit_breaker_trips"]) + 1

    def _breaker_is_open(self, host: str) -> bool:
        if not host:
            return False
        until = self._host_breaker_until_by_host.get(host, 0.0)
        if until <= 0.0:
            return False
        now = time.monotonic()
        if now < until:
            return True
        self._host_breaker_until_by_host[host] = 0.0
        return False

    def _breaker_remaining_seconds(self, host: str) -> float:
        if not host:
            return 0.0
        until = self._host_breaker_until_by_host.get(host, 0.0)
        if until <= 0.0:
            return 0.0
        now = time.monotonic()
        if now >= until:
            self._host_breaker_until_by_host[host] = 0.0
            return 0.0
        return until - now

    @staticmethod
    def _parse_retry_after_header(value: str | None) -> float | None:
        if not value:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.isdigit():
            return max(0.0, float(trimmed))
        try:
            parsed = parsedate_to_datetime(trimmed)
        except Exception:
            try:
                parsed = dt.datetime.fromisoformat(trimmed)
            except Exception:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        delta = (parsed - dt.datetime.now(dt.timezone.utc)).total_seconds()
        return max(0.0, delta)

    @staticmethod
    def _parse_retry_after_body(text: str) -> float | None:
        if not text:
            return None
        match = _RETRY_AFTER_BODY_RE.search(text)
        if not match:
            return None
        try:
            return max(0.0, float(match.group(1)))
        except Exception:
            return None

    def _retry_delay_seconds(self, retry_after_header: str | None, text: str, attempt: int) -> float:
        delay = self._parse_retry_after_header(retry_after_header)
        if delay is None:
            delay = self._parse_retry_after_body(text)
        if delay is None:
            delay = self.backoff_base_seconds * (2 ** max(0, attempt - 1))
        delay = min(self.backoff_max_seconds, max(0.25, delay))
        jitter = random.uniform(0.0, min(1.0, delay * 0.2))
        return min(self.backoff_max_seconds, delay + jitter)

    def _validation_failure_reason(
        self,
        status_code: int,
        text: str,
        require_any: tuple[str, ...],
        reject_any: tuple[str, ...],
    ) -> str | None:
        if status_code != 200:
            return f"http_status_{status_code}"
        if self._contains_any_marker(text, _POISON_BODY_MARKERS):
            return "poison_body"
        if reject_any and self._contains_any_marker(text, reject_any):
            return "rejected_marker"
        if require_any and not self._contains_any_marker(text, require_any):
            return "missing_required_marker"
        return None

    def _cache_payload(self, url: str, status_code: int, text: str, fetched_at: str) -> None:
        self._cache[url] = {
            "status_code": int(status_code),
            "text": text,
            "fetched_at": fetched_at,
        }
        self._cache_dirty = True
        self._stats["cache_writes"] = int(self._stats["cache_writes"]) + 1

    def get_text(
        self,
        url: str,
        use_cache: bool = True,
        require_any: list[str] | tuple[str, ...] | None = None,
        reject_any: list[str] | tuple[str, ...] | None = None,
    ) -> HttpResponse:
        host = urlparse(url).netloc.lower()
        required_markers = self._normalize_markers(require_any)
        rejected_markers = self._normalize_markers(reject_any)

        if use_cache:
            cached = self._cache.get(url)
            if cached is not None:
                self._stats["cache_hits"] = int(self._stats["cache_hits"]) + 1
                cached_status = int(cached.get("status_code", 0))
                cached_text = str(cached.get("text", ""))
                cached_fetched_at = str(cached.get("fetched_at", ""))
                cached_failure = self._validation_failure_reason(
                    status_code=cached_status,
                    text=cached_text,
                    require_any=required_markers,
                    reject_any=rejected_markers,
                )
                if cached_failure is None and not self._is_poisoned_response(cached_status, cached_text):
                    return HttpResponse(
                        url=url,
                        status_code=cached_status,
                        text=cached_text,
                        fetched_at=cached_fetched_at,
                        from_cache=True,
                    )
                # Purge poisoned or validation-incompatible cache rows and refetch.
                self._cache.pop(url, None)
                self._cache_dirty = True
                self._stats["cache_invalidated_runtime"] = int(self._stats["cache_invalidated_runtime"]) + 1

        self._stats["cache_misses"] = int(self._stats["cache_misses"]) + 1
        max_attempts = max(1, self.max_validation_retries + 1)

        last_status = 0
        last_text = ""
        last_fetched_at = now_iso()

        initial_breaker_wait = self._breaker_remaining_seconds(host)
        if initial_breaker_wait > 0.0:
            self._stats["circuit_breaker_short_circuits"] = int(self._stats["circuit_breaker_short_circuits"]) + 1
            time.sleep(initial_breaker_wait)

        for attempt in range(1, max_attempts + 1):
            breaker_wait = self._breaker_remaining_seconds(host)
            if breaker_wait > 0.0:
                self._stats["circuit_breaker_short_circuits"] = int(
                    self._stats["circuit_breaker_short_circuits"]
                ) + 1
                time.sleep(breaker_wait)
            retry_after_header: str | None = None
            try:
                self._respect_host_interval(url)
                self._stats["network_requests"] = int(self._stats["network_requests"]) + 1
                response = self.session.get(url, timeout=self.timeout_seconds)
                retry_after_header = response.headers.get("Retry-After")
                last_status = int(response.status_code)
                last_text = response.text or ""
                last_fetched_at = now_iso()
            except requests.RequestException:
                self._stats["request_exceptions"] = int(self._stats["request_exceptions"]) + 1
                self._record_host_transient_failure(host)
                last_status = 0
                last_text = ""
                last_fetched_at = now_iso()
                if attempt < max_attempts:
                    delay = self._retry_delay_seconds(None, "", attempt)
                    self._stats["retry_count"] = int(self._stats["retry_count"]) + 1
                    self._stats["retry_sleep_seconds"] = float(self._stats["retry_sleep_seconds"]) + delay
                    self._set_host_cooldown(url, delay)
                    time.sleep(delay)
                    continue
                return HttpResponse(
                    url=url,
                    status_code=0,
                    text="",
                    fetched_at=last_fetched_at,
                    from_cache=False,
                )

            failure = self._validation_failure_reason(
                status_code=last_status,
                text=last_text,
                require_any=required_markers,
                reject_any=rejected_markers,
            )
            if failure is None:
                self._record_host_success(host)
                self._cache_payload(url, last_status, last_text, last_fetched_at)
                return HttpResponse(
                    url=url,
                    status_code=last_status,
                    text=last_text,
                    fetched_at=last_fetched_at,
                    from_cache=False,
                )

            self._stats["validation_failures"] = int(self._stats["validation_failures"]) + 1
            is_rate_limit = self._is_rate_limited_response(last_status, last_text)
            if is_rate_limit:
                self._stats["rate_limit_events"] = int(self._stats["rate_limit_events"]) + 1

            if self._is_poisoned_response(last_status, last_text):
                self._stats["poison_responses_discarded"] = int(self._stats["poison_responses_discarded"]) + 1

            if (
                last_status in _RETRYABLE_STATUS_CODES
                or failure in {"poison_body", "rejected_marker", "missing_required_marker"}
                or is_rate_limit
            ):
                self._record_host_transient_failure(host)
            else:
                self._record_host_success(host)

            retryable = (
                attempt < max_attempts
                and (
                    last_status in _RETRYABLE_STATUS_CODES
                    or failure in {"poison_body", "rejected_marker", "missing_required_marker"}
                )
            )
            if retryable:
                delay = self._retry_delay_seconds(retry_after_header, last_text, attempt)
                self._stats["retry_count"] = int(self._stats["retry_count"]) + 1
                self._stats["retry_sleep_seconds"] = float(self._stats["retry_sleep_seconds"]) + delay
                self._set_host_cooldown(url, delay)
                time.sleep(delay)
                continue

            # Cache stable non-poison failures (e.g., 404), avoid caching transient/poison pages.
            if not self._is_poisoned_response(last_status, last_text):
                self._cache_payload(url, last_status, last_text, last_fetched_at)

            return HttpResponse(
                url=url,
                status_code=last_status,
                text=last_text,
                fetched_at=last_fetched_at,
                from_cache=False,
            )

        return HttpResponse(
            url=url,
            status_code=last_status,
            text=last_text,
            fetched_at=last_fetched_at,
            from_cache=False,
        )

    def stats(self) -> dict[str, int | float]:
        out = dict(self._stats)
        out["cache_entries_active"] = len(self._cache)
        return out

    def close(self) -> None:
        self._save_cache()
        self.session.close()
