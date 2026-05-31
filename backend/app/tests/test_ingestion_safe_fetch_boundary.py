"""Boundary tests for the ingestion safe-fetch layer.

Verifies that:
1. ``parse_allowed_domains`` handles edge cases gracefully.
2. ``fetch_for_ingestion`` propagates SSRF-blocked URLs as ``result.error``.
3. ``fetch_for_ingestion`` propagates disallowed-domain errors as ``result.error``.
4. The AST guard script exits 1 when a hypothetical bad adapter imports httpx.
5. Adapters accept and use an injected ``fetcher`` callable end-to-end.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ingestion.fetcher import (
    FetchCallable,
    fetch_for_ingestion,
    parse_allowed_domains,
)
from app.services.source_fetcher import FetchResult

# ---------------------------------------------------------------------------
# parse_allowed_domains
# ---------------------------------------------------------------------------


class TestParseAllowedDomains:
    def test_returns_list_from_valid_json(self) -> None:
        result = parse_allowed_domains('["api.canlii.org", "www.canlii.org"]')
        assert result == ["api.canlii.org", "www.canlii.org"]

    def test_returns_empty_list_for_none(self) -> None:
        assert parse_allowed_domains(None) == []

    def test_returns_empty_list_for_empty_string(self) -> None:
        assert parse_allowed_domains("") == []

    def test_returns_empty_list_for_malformed_json(self) -> None:
        assert parse_allowed_domains("{not valid json}") == []

    def test_returns_empty_list_for_non_list_json(self) -> None:
        assert parse_allowed_domains('{"key": "value"}') == []

    def test_coerces_values_to_str(self) -> None:
        result = parse_allowed_domains("[1, 2, 3]")
        assert result == ["1", "2", "3"]


# ---------------------------------------------------------------------------
# fetch_for_ingestion — SSRF / domain blocking
# ---------------------------------------------------------------------------


def _make_error_result(url: str, msg: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=None,
        fetched_at=datetime.now(timezone.utc),
        http_status=None,
        content_type=None,
        headers={},
        raw_content=None,
        raw_content_hash=None,
        extracted_text=None,
        extracted_text_hash=None,
        error=msg,
    )


class TestFetchForIngestionBlocking:
    """These tests rely on safe_fetch to reject forbidden URLs without network."""

    def test_localhost_is_blocked(self) -> None:
        result = fetch_for_ingestion("http://localhost/admin")
        assert result.error is not None
        assert result.raw_content is None

    def test_private_ip_is_blocked(self) -> None:
        result = fetch_for_ingestion("http://192.168.0.1/secret")
        assert result.error is not None
        assert result.raw_content is None

    def test_loopback_ip_is_blocked(self) -> None:
        result = fetch_for_ingestion("http://127.0.0.1/")
        assert result.error is not None

    def test_disallowed_domain_is_blocked(self) -> None:
        result = fetch_for_ingestion(
            "https://evil.example.com/data",
            allowed_domains=["api.canlii.org"],
        )
        assert result.error is not None
        assert result.raw_content is None

    def test_non_http_scheme_is_blocked(self) -> None:
        result = fetch_for_ingestion("ftp://example.com/file.zip")
        assert result.error is not None


# ---------------------------------------------------------------------------
# AST guard script
# ---------------------------------------------------------------------------


class TestAstGuardScript:
    _GUARD = (
        Path(__file__).parent.parent.parent
        / "scripts"
        / "check_no_direct_ingestion_network_clients.py"
    )

    def test_guard_script_exits_0_on_clean_adapters(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(self._GUARD)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_guard_script_exits_1_for_bad_import(self, tmp_path: Path) -> None:
        """Create a temp adapter file that imports httpx and point the guard at it."""
        bad_adapter = tmp_path / "bad_adapter.py"
        bad_adapter.write_text(
            textwrap.dedent(
                """\
                import httpx

                class BadAdapter:
                    def fetch(self):
                        return httpx.get("https://example.com")
                """
            )
        )
        # Run the guard with the adapters dir overridden via env-agnostic hack:
        # We pass the path directly as a string arg and monkeypatch is not
        # available here, so we test by running with a one-line entrypoint that
        # imports and calls _check_file directly.
        snippet = textwrap.dedent(
            f"""\
            import sys
            sys.path.insert(0, r"{self._GUARD.parent.parent}")
            from scripts.check_no_direct_ingestion_network_clients import _check_file
            from pathlib import Path
            violations = _check_file(Path(r"{bad_adapter}"))
            sys.exit(0 if not violations else 1)
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1, (
            f"Expected guard to detect httpx import but it passed.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


# ---------------------------------------------------------------------------
# Adapter fetcher injection end-to-end
# ---------------------------------------------------------------------------


def _make_ok_fetcher(content: bytes, content_type: str = "text/html") -> FetchCallable:
    """Return a no-network FetchCallable that always succeeds."""

    def _fetcher(url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=url,
            fetched_at=datetime.now(timezone.utc),
            http_status=200,
            content_type=content_type,
            headers={"content-type": content_type},
            raw_content=content,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=None,
        )

    return _fetcher


def _make_error_fetcher(error_msg: str = "domain not allowed") -> FetchCallable:
    """Return a no-network FetchCallable that always returns an error."""

    def _fetcher(url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=None,
            fetched_at=datetime.now(timezone.utc),
            http_status=None,
            content_type=None,
            headers={},
            raw_content=None,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=error_msg,
        )

    return _fetcher


class TestAdapterFetcherInjection:
    """Smoke tests that adapters honour the injected fetcher callable."""

    def test_sk_courts_adapter_uses_injected_fetcher(self) -> None:
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        fetcher = _make_ok_fetcher(
            b'{"cases": [{"title": "T", "url": "https://www.canlii.org/en/sk/skkb/doc/2026/x/x.html", "caseId": {"en": "x"}}]}',
            content_type="application/json",
        )
        adapter = CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key="fake-api-key",
            databases=["skkb"],
            result_count=10,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
            fetcher=fetcher,
        )
        raw = adapter.fetch()
        # Fetcher was called — no network error raised
        assert isinstance(raw, list)
        assert len(raw) == 1

    def test_sk_courts_adapter_returns_empty_on_fetch_error(self) -> None:
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        adapter = CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key="fake-api-key",
            databases=["skkb"],
            result_count=10,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
            fetcher=_make_error_fetcher(),
        )
        raw = adapter.fetch()
        assert raw == []

    def test_laws_justice_adapter_uses_injected_fetcher(self) -> None:
        from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter

        content = b"<html><body><table><tr><td>No data</td></tr></table></body></html>"
        adapter = LawsJusticeHtmlAdapter(
            source_key="laws_test",
            base_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            allowed_domains_json='["laws-lois.justice.gc.ca"]',
            public_record_authority="official_legislation",
            fetcher=_make_ok_fetcher(content),
        )
        raw = adapter.fetch()
        assert isinstance(raw, list)

    def test_scc_lexum_adapter_uses_injected_fetcher(self) -> None:
        from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter

        rss = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
        <item><title>Test v Canada</title><link>https://decisions.scc-csc.ca/1</link>
        <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
        </channel></rss>"""
        adapter = SCCLexumApiAdapter(
            source_key="scc_test",
            base_url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
            allowed_domains_json='["decisions.scc-csc.ca"]',
            public_record_authority="official_court_record",
            fetcher=_make_ok_fetcher(rss, content_type="application/rss+xml"),
        )
        raw = adapter.fetch()
        assert len(raw) == 1
        assert raw[0].get("title") == "Test v Canada"
