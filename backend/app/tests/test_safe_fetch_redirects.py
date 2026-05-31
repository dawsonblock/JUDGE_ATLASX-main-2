"""Redirect and central fetch policy tests for SSRF-safe ingestion paths."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.fetcher import fetch_for_ingestion
from app.services.source_fetcher import FetchResult, _SSRFRedirectHandler, fetch_source


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type

    def items(self):
        return []


class _FakeResponse(AbstractContextManager):
    status = 200

    def __init__(self, content_type: str, body: bytes) -> None:
        self.headers = _FakeHeaders(content_type)
        self._body = body

    def geturl(self) -> str:
        return "https://allowed.example/final"

    def read(self, _n: int) -> bytes:
        return self._body

    def __exit__(self, exc_type, exc, tb):
        return False


def _ok_result(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        fetched_at=datetime.now(timezone.utc),
        http_status=200,
        content_type="application/json",
        headers={},
        raw_content=b"{}",
        raw_content_hash=None,
        extracted_text=None,
        extracted_text_hash=None,
        error=None,
    )


def test_redirect_handler_blocks_disallowed_scheme_redirect() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with patch(
        "app.services.source_fetcher._is_safe_url",
        return_value=(False, "scheme 'ftp' not allowed"),
    ):
        with pytest.raises(urllib.request.HTTPError) as exc_info:
            handler.redirect_request(
                req,
                None,
                302,
                "Found",
                {},
                "ftp://allowed.example/payload",
            )

    assert "Redirect blocked" in str(exc_info.value)


def test_fetch_source_blocks_unsupported_content_type() -> None:
    fake_opener = MagicMock()
    fake_opener.open.return_value = _FakeResponse("image/png", b"\x89PNG")

    with (
        patch("app.services.source_fetcher._is_safe_url", return_value=(True, "")),
        patch("app.services.source_fetcher._build_fetch_opener", return_value=fake_opener),
    ):
        result = fetch_source(
            "https://allowed.example/image",
            store_snapshot=False,
            allowed_domains=frozenset({"allowed.example"}),
        )

    assert result.error is not None
    assert "unsupported content type" in result.error.lower()
    assert result.raw_content is None


def test_fetch_source_blocks_oversized_body() -> None:
    fake_opener = MagicMock()
    fake_opener.open.return_value = _FakeResponse("text/plain", b"x" * 9)

    with (
        patch("app.services.source_fetcher._is_safe_url", return_value=(True, "")),
        patch("app.services.source_fetcher._build_fetch_opener", return_value=fake_opener),
    ):
        result = fetch_source(
            "https://allowed.example/large",
            max_bytes=8,
            store_snapshot=False,
            allowed_domains=frozenset({"allowed.example"}),
        )

    assert result.error is not None
    assert "max_bytes" in result.error
    assert result.raw_content is None


def test_fetch_for_ingestion_passes_allowlist_and_limits_to_safe_fetch() -> None:
    with patch("app.ingestion.fetcher.safe_fetch", return_value=_ok_result("https://allowed.example/feed")) as safe_fetch:
        result = fetch_for_ingestion(
            "https://allowed.example/feed",
            allowed_domains=["allowed.example", "api.allowed.example"],
            timeout_seconds=12,
            max_bytes=1234,
        )

    assert result.error is None
    safe_fetch.assert_called_once()
    called_config = safe_fetch.call_args.args[1]
    assert called_config.allowed_domains == frozenset(
        {"allowed.example", "api.allowed.example"}
    )
    assert called_config.timeout_seconds == 12
    assert called_config.max_response_bytes == 1234
    assert called_config.store_snapshot is False


def test_fetch_for_ingestion_appends_query_params() -> None:
    with patch("app.ingestion.fetcher.safe_fetch", return_value=_ok_result("https://allowed.example/feed?page=1")) as safe_fetch:
        fetch_for_ingestion(
            "https://allowed.example/feed",
            allowed_domains=["allowed.example"],
            params={"page": 1, "format": "json"},
        )

    called_url = safe_fetch.call_args.args[0]
    assert called_url.startswith("https://allowed.example/feed?")
    assert "page=1" in called_url
    assert "format=json" in called_url
