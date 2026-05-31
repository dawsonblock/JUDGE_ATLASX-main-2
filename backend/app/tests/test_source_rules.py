"""Tests for source_rules.py safety gating.

Verifies domain allow-listing, record-type gating, and publish-gate checks
all correctly block or permit operations according to authority tier.
"""

from __future__ import annotations

import json

import pytest

from app.ingestion.source_rules import (
    RuleViolation,
    check_domain_allowed,
    check_publish_gate,
    check_record_type_allowed,
    enforce_all,
)

# ── check_domain_allowed ─────────────────────────────────────────────────────


class TestCheckDomainAllowed:
    def test_empty_allowed_list_blocks_any(self) -> None:
        # Empty allowlist → no domain can match → fail-closed
        result = check_domain_allowed("https://example.com/data.csv", "[]")
        assert isinstance(result, RuleViolation)
        assert result.rule == "domain_allowlist"

    def test_matching_domain_permits(self) -> None:
        domains = json.dumps(["opendata.saskatoon.ca"])
        result = check_domain_allowed(
            "https://opendata.saskatoon.ca/api/records", domains
        )
        assert result is None

    def test_non_matching_domain_blocks(self) -> None:
        domains = json.dumps(["opendata.saskatoon.ca"])
        result = check_domain_allowed("https://evil.example.com/data", domains)
        assert isinstance(result, RuleViolation)
        assert "not in allowed" in result.detail

    def test_none_allowed_domains_blocks(self) -> None:
        # None allowed_domains → fail-closed: no allowlist configured
        result = check_domain_allowed("https://example.com/", None)
        assert isinstance(result, RuleViolation)
        assert "No allowed_domains" in result.detail

    def test_invalid_url_blocks(self) -> None:
        domains = json.dumps(["opendata.saskatoon.ca"])
        result = check_domain_allowed("not-a-url", domains)
        assert isinstance(result, RuleViolation)

    def test_ssrf_private_ip_blocked(self) -> None:
        # SSRF block fires before the domain allowlist check
        domains = json.dumps(["192.168.1.1"])
        result = check_domain_allowed("http://192.168.1.1/internal", domains)
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"


# ── SSRF blocking ────────────────────────────────────────────────────────────


class TestSsrfBlocking:
    """Verify _is_private_or_loopback fires before the domain allowlist."""

    def test_loopback_ipv4_blocked(self) -> None:
        result = check_domain_allowed(
            "http://127.0.0.1/admin", json.dumps(["127.0.0.1"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_loopback_ipv6_blocked(self) -> None:
        result = check_domain_allowed("http://[::1]/secret", json.dumps(["::1"]))
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_rfc1918_10_blocked(self) -> None:
        result = check_domain_allowed("http://10.0.0.1/data", json.dumps(["10.0.0.1"]))
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_rfc1918_172_blocked(self) -> None:
        result = check_domain_allowed(
            "http://172.16.0.1/data", json.dumps(["172.16.0.1"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_rfc1918_192_168_blocked(self) -> None:
        result = check_domain_allowed(
            "http://192.168.0.1/data", json.dumps(["192.168.0.1"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_localhost_string_blocked(self) -> None:
        result = check_domain_allowed(
            "http://localhost/admin", json.dumps(["localhost"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_link_local_metadata_blocked(self) -> None:
        # AWS/GCP metadata endpoint
        result = check_domain_allowed(
            "http://169.254.169.254/latest/meta-data", json.dumps(["169.254.169.254"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "ssrf_block"

    def test_public_ip_passes_ssrf_check(self) -> None:
        # A public IP in the allowlist must NOT be blocked by SSRF guard
        result = check_domain_allowed("http://8.8.8.8/data", json.dumps(["8.8.8.8"]))
        assert result is None

    def test_public_hostname_passes(self) -> None:
        result = check_domain_allowed(
            "https://opendata.saskatoon.ca/api", json.dumps(["opendata.saskatoon.ca"])
        )
        assert result is None

    def test_ftp_scheme_blocked_before_ssrf_check(self) -> None:
        # ftp:// is blocked by scheme check, not SSRF check
        result = check_domain_allowed(
            "ftp://opendata.saskatoon.ca/file", json.dumps(["opendata.saskatoon.ca"])
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "domain_allowlist"

    def test_no_allowlist_blocks_public_ip_too(self) -> None:
        # Without an allowlist, even public IPs are refused
        result = check_domain_allowed("http://8.8.8.8/data", None)
        assert isinstance(result, RuleViolation)
        assert result.rule == "domain_allowlist"


# ── check_record_type_allowed ────────────────────────────────────────────────


class TestCheckRecordTypeAllowed:
    def test_official_open_data_may_create_crime_incident(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "official_open_data", '["CrimeIncident", "ReviewItem"]'
        )
        assert result is None

    def test_news_context_cannot_create_crime_incident(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "news_context", '["CrimeIncident"]'
        )
        assert isinstance(result, RuleViolation)
        assert (
            "not permitted" in result.detail.lower() or "CrimeIncident" in result.detail
        )

    def test_news_context_may_create_review_item(self) -> None:
        result = check_record_type_allowed(
            "ReviewItem", "news_context", '["ReviewItem"]'
        )
        assert result is None

    def test_unknown_authority_blocked_from_crime_incident(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "unknown", '["CrimeIncident"]'
        )
        assert isinstance(result, RuleViolation)

    def test_official_court_record_cannot_create_crime_incident(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "official_court_record", '["CrimeIncident"]'
        )
        assert isinstance(result, RuleViolation)

    def test_official_legislation_cannot_create_crime_incident(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "official_legislation", '["CrimeIncident"]'
        )
        assert isinstance(result, RuleViolation)

    def test_record_type_not_in_creates_list_blocked(self) -> None:
        result = check_record_type_allowed(
            "CrimeIncident", "official_open_data", '["ReviewItem"]'
        )
        assert isinstance(result, RuleViolation)

    def test_empty_creates_list_blocks_all(self) -> None:
        result = check_record_type_allowed("CrimeIncident", "official_open_data", "[]")
        assert isinstance(result, RuleViolation)


# ── check_publish_gate ───────────────────────────────────────────────────────


class TestCheckPublishGate:
    def test_news_context_cannot_auto_publish(self) -> None:
        result = check_publish_gate(
            public_record_authority="news_context",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert isinstance(result, RuleViolation)

    def test_unknown_authority_cannot_auto_publish(self) -> None:
        result = check_publish_gate(
            public_record_authority="unknown",
            auto_publish_enabled=True,
            public_publish_default=False,
        )
        assert isinstance(result, RuleViolation)

    def test_official_statistics_eligible_for_auto_publish(self) -> None:
        # Authority in eligible set and both flags True → auto-publish allowed
        result = check_publish_gate(
            public_record_authority="official_statistics",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert result is None

    def test_official_statistics_disabled_flag_blocks_auto_publish(self) -> None:
        # Even eligible authority is blocked when the flag is off
        result = check_publish_gate(
            public_record_authority="official_statistics",
            auto_publish_enabled=False,
            public_publish_default=False,
        )
        assert isinstance(result, RuleViolation)

    def test_official_court_record_cannot_auto_publish(self) -> None:
        result = check_publish_gate(
            public_record_authority="official_court_record",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert isinstance(result, RuleViolation)


# ── enforce_all ──────────────────────────────────────────────────────────────


class TestEnforceAll:
    def test_all_violations_collected(self) -> None:
        violations = enforce_all(
            url="https://evil.example.com/data",
            allowed_domains_json=json.dumps(["opendata.saskatoon.ca"]),
            record_type="CrimeIncident",
            public_record_authority="news_context",
            creates_json='["CrimeIncident"]',
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        # Domain violation + record type violation + publish gate violation
        assert len(violations) >= 2

    def test_clean_call_returns_empty(self) -> None:
        violations = enforce_all(
            url="https://opendata.saskatoon.ca/data.csv",
            allowed_domains_json=json.dumps(["opendata.saskatoon.ca"]),
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json='["CrimeIncident", "ReviewItem"]',
            auto_publish_enabled=False,
            public_publish_default=False,
        )
        assert violations == []
