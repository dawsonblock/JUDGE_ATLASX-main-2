"""Tests for app.security.safe_fetch.

Covers:
  - is_private_ip() for all protected address ranges
  - safe_fetch() SSRF blocking before any network call is attempted
  - safe_fetch() domain allowlist enforcement
  - safe_fetch() passes through to fetch_source when policy allows
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.security.safe_fetch import SafeFetchConfig, is_private_ip, safe_fetch


# ---------------------------------------------------------------------------
# is_private_ip — unit tests (no network, no DB)
# ---------------------------------------------------------------------------


class TestIsPrivateIp:
    def test_loopback_127(self):
        assert is_private_ip("127.0.0.1") is True

    def test_rfc1918_10_block(self):
        assert is_private_ip("10.0.0.1") is True

    def test_rfc1918_192_168(self):
        assert is_private_ip("192.168.1.1") is True

    def test_rfc1918_172_16(self):
        assert is_private_ip("172.16.0.1") is True

    def test_cgnat_100_64(self):
        """CGNAT 100.64/10 is reserved and must be treated as private."""
        assert is_private_ip("100.64.0.1") is True

    def test_link_local_169_254(self):
        """Link-local (cloud metadata range) must be private."""
        assert is_private_ip("169.254.169.254") is True

    def test_public_ip_not_private(self):
        """Globally-routable public IP must pass through."""
        assert is_private_ip("8.8.8.8") is False

    def test_malformed_returns_false(self):
        """Non-IP strings must return False, not raise."""
        assert is_private_ip("not-an-ip") is False
        assert is_private_ip("") is False


# ---------------------------------------------------------------------------
# safe_fetch() — SSRF blocking (no network calls)
# ---------------------------------------------------------------------------


class TestSafeFetchBlocking:
    """safe_fetch must return an error FetchResult without opening any socket."""

    def _check_blocked(self, url: str, keyword: str) -> None:
        result = safe_fetch(url, SafeFetchConfig(store_snapshot=False))
        assert result.raw_content is None, "raw_content must be None when blocked"
        assert result.error is not None, "error must be set when blocked"
        assert keyword.lower() in result.error.lower(), (
            f"Expected '{keyword}' in error: {result.error!r}"
        )

    def test_blocks_private_ip_10(self):
        self._check_blocked("http://10.0.0.1/path", "SSRF")

    def test_blocks_private_ip_192_168(self):
        self._check_blocked("http://192.168.0.1/admin", "SSRF")

    def test_blocks_cloud_metadata(self):
        self._check_blocked("http://169.254.169.254/latest/meta-data/", "SSRF")

    def test_blocks_ftp_scheme(self):
        self._check_blocked("ftp://example.com/file.txt", "SSRF")

    def test_blocks_file_scheme(self):
        self._check_blocked("file:///etc/passwd", "SSRF")


# ---------------------------------------------------------------------------
# safe_fetch() — domain allowlist enforcement
# ---------------------------------------------------------------------------


class TestSafeFetchAllowlist:
    def test_allowlist_blocks_unlisted_domain(self):
        """A domain not in the allowlist must be rejected before network.

        Gate 1 (_is_safe_url) is patched to pass so that Gate 2 (allowlist)
        is the active gate under test.
        """
        config = SafeFetchConfig(
            allowed_domains=frozenset({"trusted.gov"}),
            store_snapshot=False,
        )
        with patch("app.security.safe_fetch._is_safe_url", return_value=(True, "")):
            result = safe_fetch("https://attacker.example.com/payload", config)
        assert result.raw_content is None
        assert result.error is not None
        assert "allowlist" in result.error.lower()

    def test_allowlist_strips_www_prefix_for_comparison(self):
        """www.example.com should match allowlist entry 'example.com'."""
        config = SafeFetchConfig(
            allowed_domains=frozenset({"example.com"}),
            store_snapshot=False,
        )
        # We patch fetch_source to avoid a real network call; the important
        # assertion is that the allowlist gate does NOT block the request.
        dummy_result = MagicMock()
        dummy_result.error = None
        with patch(
            "app.security.safe_fetch.fetch_source", return_value=dummy_result
        ) as mock_fetch:
            result = safe_fetch("https://www.example.com/page", config)
        mock_fetch.assert_called_once()

    def test_no_allowlist_passes_to_fetch_source(self):
        """Empty allowed_domains must not filter any domain."""
        config = SafeFetchConfig(store_snapshot=False)
        dummy_result = MagicMock()
        dummy_result.error = None
        with patch(
            "app.security.safe_fetch.fetch_source", return_value=dummy_result
        ) as mock_fetch:
            safe_fetch("https://8.8.8.8/", config)
        mock_fetch.assert_called_once()
