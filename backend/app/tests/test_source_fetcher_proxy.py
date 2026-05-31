"""Tests for egress proxy wiring in source_fetcher."""

from __future__ import annotations

from contextlib import AbstractContextManager
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from app.services.source_fetcher import (
    _SSRFRedirectHandler,
    _build_fetch_opener,
    fetch_source,
)


class _FakeHeaders:
    def get_content_type(self) -> str:
        return "text/plain"

    def items(self):
        return []


class _FakeResponse(AbstractContextManager):
    status = 200

    def __init__(self) -> None:
        self.headers = _FakeHeaders()

    def geturl(self) -> str:
        return "https://example.com/final"

    def read(self, _n: int) -> bytes:
        return b"ok"

    def __exit__(self, exc_type, exc, tb):
        return False


def test_build_fetch_opener_includes_proxy_handler_when_configured() -> None:
    with patch("app.services.source_fetcher.urllib.request.build_opener") as build_opener:
        _build_fetch_opener("http://proxy.local:8080")

    assert build_opener.called
    args = build_opener.call_args[0]
    assert any(type(arg).__name__ == "ProxyHandler" for arg in args)
    assert any(type(arg).__name__ == "_SSRFRedirectHandler" for arg in args)


def test_fetch_source_uses_proxy_config_for_runtime_requests(monkeypatch) -> None:
    monkeypatch.setenv("JTA_FETCH_EGRESS_PROXY", "http://proxy.local:8080")

    fake_opener = MagicMock()
    fake_opener.open.return_value = _FakeResponse()

    with (
        patch("app.services.source_fetcher._is_safe_url", return_value=(True, "")),
        patch(
            "app.services.source_fetcher._build_fetch_opener",
            return_value=fake_opener,
        ) as build_opener,
    ):
        result = fetch_source("https://example.com/resource", store_snapshot=False)

    build_opener.assert_called_once_with(
        "http://proxy.local:8080",
        allowed_domains=None,
    )
    assert result.error is None
    assert result.raw_content == b"ok"


def test_redirect_same_allowed_domain_passes() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with (
        patch("app.services.source_fetcher._is_safe_url", return_value=(True, "")),
        patch(
            "urllib.request.HTTPRedirectHandler.redirect_request",
            return_value="ok",
        ) as parent_redirect,
    ):
        result = handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "https://allowed.example/next",
        )

    parent_redirect.assert_called_once()
    assert result == "ok"


def test_redirect_disallowed_public_domain_fails() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with patch("app.services.source_fetcher._is_safe_url", return_value=(True, "")):
        with pytest.raises(urllib.request.HTTPError) as exc:
            handler.redirect_request(
                req,
                None,
                302,
                "Found",
                {},
                "https://disallowed.example/path",
            )

    assert "not in allowlist" in str(exc.value)


def test_redirect_to_localhost_fails() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with pytest.raises(urllib.request.HTTPError) as exc:
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://localhost/internal",
        )

    assert "Redirect blocked" in str(exc.value)


def test_redirect_to_private_ip_fails() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with pytest.raises(urllib.request.HTTPError) as exc:
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://10.0.0.42/",
        )

    assert "Redirect blocked" in str(exc.value)


def test_redirect_to_cloud_metadata_fails() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with pytest.raises(urllib.request.HTTPError) as exc:
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://169.254.169.254/latest/meta-data/",
        )

    assert "Redirect blocked" in str(exc.value)


def test_redirect_https_to_http_downgrade_fails() -> None:
    req = urllib.request.Request("https://allowed.example/start")
    handler = _SSRFRedirectHandler(allowed_domains=frozenset({"allowed.example"}))

    with pytest.raises(urllib.request.HTTPError) as exc:
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://allowed.example/next",
        )

    assert "downgrade" in str(exc.value).lower()


def test_redirect_handler_limits_redirect_depth() -> None:
    assert _SSRFRedirectHandler.max_redirections == 5
