from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core.http_client import CachedHttpClient  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, text: str, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)

    def close(self) -> None:
        pass


class CachedHttpClientTests(unittest.TestCase):
    def test_rate_limit_response_uses_explicit_retry_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            client = CachedHttpClient(
                timeout_seconds=1,
                max_retries=0,
                max_validation_retries=1,
                backoff_base_seconds=0.1,
                backoff_max_seconds=0.1,
                user_agent="test",
                cache_path=Path(tmpdir) / "cache.json",
                host_min_interval=0.0,
            )
            session = FakeSession(
                [
                    FakeResponse(429, "too many requests"),
                    FakeResponse(200, "<feed></feed>"),
                ]
            )
            client.session = session  # type: ignore[assignment]

            with mock.patch("core.http_client.time.sleep") as sleep:
                response = client.get_text(
                    "https://export.arxiv.org/api/query?search_query=ti:test",
                    use_cache=False,
                    require_any=["<feed"],
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(session.calls, 2)
            self.assertEqual(client.stats()["rate_limit_events"], 1)
            self.assertEqual(client.stats()["retry_count"], 1)
            self.assertGreaterEqual(sleep.call_count, 1)
            self.assertEqual(sleep.call_args_list[0], mock.call(0.1))
            client.close()


if __name__ == "__main__":
    unittest.main()
