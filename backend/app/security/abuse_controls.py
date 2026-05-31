"""Security and abuse controls (Phase 19).

Provides abuse detection and security monitoring.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class AbuseDetector:
    """Detects potential abuse patterns in API requests."""

    def __init__(self):
        self.request_history: Dict[str, List[datetime]] = defaultdict(list)
        self.failed_attempts: Dict[str, int] = defaultdict(int)

    def check_rate_abuse(
        self,
        client_id: str,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Check if client is abusing rate limits.

        Args:
            client_id: Client identifier
            max_requests: Maximum allowed requests
            window_seconds: Time window in seconds

        Returns:
            Abuse check result
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        # Clean old requests
        self.request_history[client_id] = [
            ts for ts in self.request_history[client_id]
            if ts > cutoff
        ]

        request_count = len(self.request_history[client_id])
        is_abuse = request_count > max_requests

        return {
            "is_abuse": is_abuse,
            "request_count": request_count,
            "max_allowed": max_requests,
            "window_seconds": window_seconds,
        }

    def check_failed_login_abuse(
        self,
        client_id: str,
        max_failures: int = 5,
        window_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Check if client has excessive failed login attempts.

        Args:
            client_id: Client identifier
            max_failures: Maximum allowed failures
            window_seconds: Time window in seconds

        Returns:
            Abuse check result
        """
        failure_count = self.failed_attempts.get(client_id, 0)
        is_abuse = failure_count >= max_failures

        return {
            "is_abuse": is_abuse,
            "failure_count": failure_count,
            "max_allowed": max_failures,
        }

    def record_request(self, client_id: str):
        """Record a request from a client.

        Args:
            client_id: Client identifier
        """
        self.request_history[client_id].append(
            datetime.now(timezone.utc)
        )

    def record_failure(self, client_id: str):
        """Record a failed attempt from a client.

        Args:
            client_id: Client identifier
        """
        self.failed_attempts[client_id] += 1

    def reset_failures(self, client_id: str):
        """Reset failure count for a client.

        Args:
            client_id: Client identifier
        """
        self.failed_attempts[client_id] = 0


class SecurityMonitor:
    """Monitors security events and alerts."""

    def __init__(self):
        self.alerts: List[Dict[str, Any]] = []
        self.alert_thresholds = {
            "high": 10,
            "medium": 5,
            "low": 1,
        }

    def record_alert(
        self,
        severity: str,
        event_type: str,
        client_id: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Record a security alert.

        Args:
            severity: Alert severity (high, medium, low)
            event_type: Type of security event
            client_id: Client identifier
            details: Additional event details
        """
        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "event_type": event_type,
            "client_id": client_id,
            "details": details or {},
        }
        self.alerts.append(alert)
        logger.warning(f"Security alert: {severity} - {event_type} - {client_id}")

    def get_recent_alerts(
        self,
        hours: int = 24,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent security alerts.

        Args:
            hours: Hours to look back
            severity: Filter by severity

        Returns:
            List of recent alerts
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert["timestamp"]) > cutoff
        ]

        if severity:
            filtered = [a for a in filtered if a["severity"] == severity]

        return filtered

    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of security alerts.

        Returns:
            Alert summary statistics
        """
        recent = self.get_recent_alerts(hours=24)

        severity_counts = defaultdict(int)
        for alert in recent:
            severity_counts[alert["severity"]] += 1

        return {
            "total_alerts_24h": len(recent),
            "high_severity": severity_counts.get("high", 0),
            "medium_severity": severity_counts.get("medium", 0),
            "low_severity": severity_counts.get("low", 0),
        }


def check_ip_reputation(ip_address: str) -> Dict[str, Any]:
    """Check IP address reputation.

    Args:
        ip_address: IP address to check

    Returns:
        IP reputation result
    """
    # Simplified implementation - in production use a real IP reputation service
    return {
        "ip_address": ip_address,
        "reputation": "neutral",
        "is_blacklisted": False,
        "threat_level": "low",
    }


def check_user_agent(user_agent: str) -> Dict[str, Any]:
    """Check user agent for suspicious patterns.

    Args:
        user_agent: User agent string

    Returns:
        User agent check result
    """
    suspicious_patterns = [
        "bot",
        "crawler",
        "spider",
        "scraper",
        "curl",
        "wget",
    ]

    user_agent_lower = user_agent.lower()
    is_suspicious = any(pattern in user_agent_lower for pattern in suspicious_patterns)

    return {
        "user_agent": user_agent,
        "is_suspicious": is_suspicious,
        "reason": "Suspicious pattern detected" if is_suspicious else None,
    }


def validate_request_headers(
    headers: Dict[str, str],
) -> Dict[str, Any]:
    """Validate request headers for security issues.

    Args:
        headers: Request headers dictionary

    Returns:
        Validation result
    """
    issues = []

    # Check for missing required headers
    if "user-agent" not in headers:
        issues.append("missing_user_agent")

    # Check for suspicious headers
    suspicious_headers = ["x-forwarded-for", "x-real-ip"]
    for header in suspicious_headers:
        if header in headers:
            # In production, validate these headers carefully
            pass

    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


# Global instances
abuse_detector = AbuseDetector()
security_monitor = SecurityMonitor()
