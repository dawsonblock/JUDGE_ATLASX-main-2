"""Tests for security and abuse controls (Phase 19).

Tests abuse detection, security monitoring, and IP/user agent checks.
"""

from datetime import datetime, timezone, timedelta

from app.security.abuse_controls import (
    AbuseDetector,
    SecurityMonitor,
    check_ip_reputation,
    check_user_agent,
    validate_request_headers,
    abuse_detector,
    security_monitor,
)


class TestAbuseDetector:
    """Test abuse detection functionality."""

    def test_check_rate_abuse_normal(self):
        """Test rate abuse check with normal usage."""
        detector = AbuseDetector()
        result = detector.check_rate_abuse("client1")

        assert result["is_abuse"] is False
        assert result["request_count"] == 0

    def test_check_rate_abuse_exceeded(self):
        """Test rate abuse check when limit exceeded."""
        detector = AbuseDetector()
        for _ in range(150):
            detector.record_request("client1")

        result = detector.check_rate_abuse("client1", max_requests=100)

        assert result["is_abuse"] is True
        assert result["request_count"] == 150

    def test_check_failed_login_abuse(self):
        """Test failed login abuse detection."""
        detector = AbuseDetector()
        for _ in range(6):
            detector.record_failure("client1")

        result = detector.check_failed_login_abuse("client1", max_failures=5)

        assert result["is_abuse"] is True
        assert result["failure_count"] == 6

    def test_reset_failures(self):
        """Test resetting failure count."""
        detector = AbuseDetector()
        detector.record_failure("client1")
        detector.reset_failures("client1")

        result = detector.check_failed_login_abuse("client1")
        assert result["failure_count"] == 0


class TestSecurityMonitor:
    """Test security monitoring functionality."""

    def test_record_alert(self):
        """Test recording security alerts."""
        monitor = SecurityMonitor()
        monitor.record_alert("high", "test_event", "client1")

        assert len(monitor.alerts) == 1
        assert monitor.alerts[0]["severity"] == "high"

    def test_get_recent_alerts(self):
        """Test retrieving recent alerts."""
        monitor = SecurityMonitor()
        monitor.record_alert("high", "test_event", "client1")

        recent = monitor.get_recent_alerts(hours=24)
        assert len(recent) == 1

    def test_get_recent_alerts_old(self):
        """Test retrieving alerts filters old ones."""
        monitor = SecurityMonitor()
        # Add an alert with old timestamp
        old_alert = {
            "timestamp": (
                datetime.now(timezone.utc) - timedelta(hours=25)
            ).isoformat(),
            "severity": "high",
            "event_type": "test",
            "client_id": "client1",
            "details": {},
        }
        monitor.alerts.append(old_alert)

        recent = monitor.get_recent_alerts(hours=24)
        assert len(recent) == 0

    def test_get_alert_summary(self):
        """Test getting alert summary."""
        monitor = SecurityMonitor()
        monitor.record_alert("high", "test1", "client1")
        monitor.record_alert("medium", "test2", "client2")
        monitor.record_alert("low", "test3", "client3")

        summary = monitor.get_alert_summary()
        assert summary["total_alerts_24h"] == 3
        assert summary["high_severity"] == 1
        assert summary["medium_severity"] == 1
        assert summary["low_severity"] == 1


class TestIPReputation:
    """Test IP reputation checking."""

    def test_check_ip_reputation(self):
        """Test IP reputation check."""
        result = check_ip_reputation("192.168.1.1")

        assert "ip_address" in result
        assert "reputation" in result
        assert "is_blacklisted" in result


class TestUserAgentCheck:
    """Test user agent validation."""

    def test_check_user_agent_normal(self):
        """Test normal user agent."""
        result = check_user_agent("Mozilla/5.0")

        assert result["is_suspicious"] is False

    def test_check_user_agent_suspicious(self):
        """Test suspicious user agent."""
        result = check_user_agent("curl/7.68.0")

        assert result["is_suspicious"] is True
        assert result["reason"] is not None


class TestHeaderValidation:
    """Test request header validation."""

    def test_validate_headers_valid(self):
        """Test validation of valid headers."""
        headers = {"user-agent": "Mozilla/5.0"}
        result = validate_request_headers(headers)

        assert result["valid"] is True

    def test_validate_headers_missing_ua(self):
        """Test validation detects missing user agent."""
        headers = {}
        result = validate_request_headers(headers)

        assert result["valid"] is False
        assert "missing_user_agent" in result["issues"]
