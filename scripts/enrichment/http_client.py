from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .models import now_iso


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
        user_agent: str,
        cache_path: Path,
        host_min_interval: float = 0.2,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.cache_path = cache_path
        self.host_min_interval = max(0.0, host_min_interval)
        self._cache_dirty = False
        self._cache = self._load_cache(cache_path)
        self._last_request_by_host: dict[str, float] = {}

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=0.3,
            backoff_max=5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent})

    @staticmethod
    def _load_cache(path: Path) -> dict[str, dict[str, str | int]]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        responses = data.get("responses")
        if not isinstance(responses, dict):
            return {}
        out: dict[str, dict[str, str | int]] = {}
        for url, payload in responses.items():
            if isinstance(url, str) and isinstance(payload, dict):
                out[url] = payload
        return out

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
        now = time.monotonic()
        last = self._last_request_by_host.get(host)
        if last is not None:
            delta = now - last
            if delta < self.host_min_interval:
                time.sleep(self.host_min_interval - delta)
        self._last_request_by_host[host] = time.monotonic()

    def get_text(self, url: str, use_cache: bool = True) -> HttpResponse:
        if use_cache:
            cached = self._cache.get(url)
            if cached is not None:
                return HttpResponse(
                    url=url,
                    status_code=int(cached.get("status_code", 0)),
                    text=str(cached.get("text", "")),
                    fetched_at=str(cached.get("fetched_at", "")),
                    from_cache=True,
                )

        self._respect_host_interval(url)
        response = self.session.get(url, timeout=self.timeout_seconds)
        fetched_at = now_iso()
        payload = {
            "status_code": int(response.status_code),
            "text": response.text,
            "fetched_at": fetched_at,
        }
        self._cache[url] = payload
        self._cache_dirty = True

        return HttpResponse(
            url=url,
            status_code=response.status_code,
            text=response.text,
            fetched_at=fetched_at,
            from_cache=False,
        )

    def close(self) -> None:
        self._save_cache()
        self.session.close()
