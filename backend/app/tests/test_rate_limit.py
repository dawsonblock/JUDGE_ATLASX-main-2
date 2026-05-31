"""Tests for the simple in-memory rate limiter."""

from app.core.rate_limit import SimpleRateLimiter, get_rate_limiter


class TestSimpleRateLimiter:
    """Test the SimpleRateLimiter class."""

    def test_check_allows_requests_under_limit(self):
        """Requests under the limit should be allowed."""
        limiter = SimpleRateLimiter()
        
        # Allow 3 requests
        for i in range(3):
            assert limiter.check("test_ip", limit=5) is True

    def test_check_blocks_requests_over_limit(self):
        """Requests over the limit should be blocked."""
        limiter = SimpleRateLimiter()
        
        # Allow 3 requests
        for i in range(3):
            assert limiter.check("test_ip", limit=3) is True
        
        # 4th request should be blocked
        assert limiter.check("test_ip", limit=3) is False

    def test_different_ips_have_separate_limits(self):
        """Different IP addresses should have separate rate limits."""
        limiter = SimpleRateLimiter()
        
        # IP1 makes 3 requests
        for i in range(3):
            assert limiter.check("192.168.1.1", limit=3) is True
        assert limiter.check("192.168.1.1", limit=3) is False
        
        # IP2 should still be allowed
        for i in range(3):
            assert limiter.check("192.168.1.2", limit=3) is True

    def test_old_requests_expire_after_window(self):
        """Old requests outside the time window should not count."""
        import time
        limiter = SimpleRateLimiter()
        
        # Make 3 requests
        for i in range(3):
            assert limiter.check("test_ip", limit=3) is True
        assert limiter.check("test_ip", limit=3) is False
        
        # Wait for window to expire (1 second window for testing)
        time.sleep(1.1)
        
        # New request should be allowed
        assert limiter.check("test_ip", limit=3, window=1) is True

    def test_reset_clears_specific_key(self):
        """Reset should clear requests for a specific key."""
        limiter = SimpleRateLimiter()
        
        # Make 3 requests
        for i in range(3):
            assert limiter.check("test_ip", limit=3) is True
        assert limiter.check("test_ip", limit=3) is False
        
        # Reset the key
        limiter.reset("test_ip")
        
        # Should be allowed again
        assert limiter.check("test_ip", limit=3) is True

    def test_reset_clears_all_keys(self):
        """Reset with None should clear all keys."""
        limiter = SimpleRateLimiter()
        
        # Make requests from multiple IPs
        for i in range(3):
            limiter.check("192.168.1.1", limit=3)
            limiter.check("192.168.1.2", limit=3)
        
        # Reset all
        limiter.reset()
        
        # Both IPs should be allowed again
        assert limiter.check("192.168.1.1", limit=3) is True
        assert limiter.check("192.168.1.2", limit=3) is True

    def test_get_rate_limiter_returns_singleton(self):
        """get_rate_limiter should return the same instance."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        
        assert limiter1 is limiter2


class TestTrustedProxyIP:
    """Test that X-Forwarded-For is only trusted from configured proxy IPs."""

    def _make_request(self, direct_ip: str, forwarded_for: str | None = None) -> object:
        """Build a minimal mock Request."""
        from unittest.mock import MagicMock
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = direct_ip
        headers = {}
        if forwarded_for:
            headers["X-Forwarded-For"] = forwarded_for
        req.headers = headers
        return req

    def test_untrusted_proxy_ignores_forwarded_for(self, monkeypatch):
        """If direct IP is not in trusted list, X-Forwarded-For is ignored."""
        from unittest.mock import patch

        class FakeSettings:
            trusted_proxy_ips = "10.0.0.1"
            rate_limit_enabled = True
            rate_limit_backend = "memory"
            redis_url = None

        with patch("app.core.rate_limit.get_settings", return_value=FakeSettings()):
            from app.core.rate_limit import _get_client_ip
            req = self._make_request("8.8.8.8", forwarded_for="1.2.3.4")
            ip = _get_client_ip(req)
            assert ip == "8.8.8.8", f"Should use direct IP when proxy is not trusted, got {ip}"

    def test_trusted_proxy_uses_forwarded_for(self, monkeypatch):
        """If direct IP is in trusted list, X-Forwarded-For leftmost IP is used."""
        from unittest.mock import patch

        class FakeSettings:
            trusted_proxy_ips = "10.0.0.1"
            rate_limit_enabled = True
            rate_limit_backend = "memory"
            redis_url = None

        with patch("app.core.rate_limit.get_settings", return_value=FakeSettings()):
            from app.core.rate_limit import _get_client_ip
            req = self._make_request("10.0.0.1", forwarded_for="1.2.3.4, 10.0.0.1")
            ip = _get_client_ip(req)
            assert ip == "1.2.3.4", f"Should use leftmost X-Forwarded-For IP, got {ip}"

    def test_no_trusted_proxies_uses_direct_ip(self, monkeypatch):
        """With empty trusted_proxy_ips, always use direct connection IP."""
        from unittest.mock import patch

        class FakeSettings:
            trusted_proxy_ips = ""
            rate_limit_enabled = True
            rate_limit_backend = "memory"
            redis_url = None

        with patch("app.core.rate_limit.get_settings", return_value=FakeSettings()):
            from app.core.rate_limit import _get_client_ip
            req = self._make_request("203.0.113.1", forwarded_for="1.2.3.4")
            ip = _get_client_ip(req)
            assert ip == "203.0.113.1"

