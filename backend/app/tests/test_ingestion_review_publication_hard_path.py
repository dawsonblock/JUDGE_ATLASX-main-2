"""Integration tests: ingestion → review queue → publication gate hard path.

Tests the end-to-end rule chain implemented in source_rules.py:

    check_domain_allowed  →  check_record_type_allowed  →  check_publish_gate
                                                          ↑
                                                    enforce_all()

No database, no HTTP — all source_rules functions are pure.
"""

from __future__ import annotations

import json

from app.ingestion.source_rules import (
    RuleViolation,
    check_publish_gate,
    check_record_type_allowed,
    enforce_all,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _creates(record_type: str) -> str:
    return json.dumps([record_type])


# ---------------------------------------------------------------------------
# Record-type gate
# ---------------------------------------------------------------------------


class TestRecordTypeGate:
    """check_record_type_allowed across authority levels and creates declarations."""

    def test_official_open_data_allows_crime_incident(self) -> None:
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json=_creates("CrimeIncident"),
        )
        assert result is None

    def test_official_open_data_allows_review_item(self) -> None:
        result = check_record_type_allowed(
            record_type="ReviewItem",
            public_record_authority="official_open_data",
            creates_json=_creates("ReviewItem"),
        )
        assert result is None

    def test_news_context_blocks_crime_incident(self) -> None:
        """news_context authority must never create CrimeIncident directly."""
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="news_context",
            creates_json=_creates("CrimeIncident"),
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "authority_record_type"
        assert "news_context" in result.detail

    def test_news_context_allows_review_item(self) -> None:
        result = check_record_type_allowed(
            record_type="ReviewItem",
            public_record_authority="news_context",
            creates_json=_creates("ReviewItem"),
        )
        assert result is None

    def test_unknown_authority_blocks_crime_incident(self) -> None:
        """Unrecognised authorities fall back to the most restrictive tier."""
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="unrecognized_authority",
            creates_json=None,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "authority_record_type"

    def test_creates_declaration_mismatch_is_blocked(self) -> None:
        """An authority-allowed type is still blocked if not in the creates list."""
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json=_creates("ReviewItem"),  # CrimeIncident NOT declared
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "creates_declaration"

    def test_null_creates_does_not_restrict(self) -> None:
        """A null creates list imposes no declaration constraint."""
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json=None,
        )
        assert result is None

    def test_official_legislation_blocks_crime_incident(self) -> None:
        """official_legislation sources may only produce ReviewItem."""
        result = check_record_type_allowed(
            record_type="CrimeIncident",
            public_record_authority="official_legislation",
            creates_json=None,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "authority_record_type"


# ---------------------------------------------------------------------------
# Publish gate
# ---------------------------------------------------------------------------


class TestPublishGate:
    """check_publish_gate across authority and flag combinations."""

    def test_eligible_authority_all_flags_on_passes(self) -> None:
        result = check_publish_gate(
            public_record_authority="official_open_data",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert result is None

    def test_auto_publish_disabled_blocks(self) -> None:
        result = check_publish_gate(
            public_record_authority="official_open_data",
            auto_publish_enabled=False,
            public_publish_default=True,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "publish_gate_flag"

    def test_public_publish_default_false_blocks(self) -> None:
        result = check_publish_gate(
            public_record_authority="official_open_data",
            auto_publish_enabled=True,
            public_publish_default=False,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "publish_gate_default"

    def test_news_context_is_not_eligible(self) -> None:
        result = check_publish_gate(
            public_record_authority="news_context",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "publish_gate_authority"

    def test_official_court_record_is_not_eligible(self) -> None:
        """official_court_record is not in the auto-publish eligible set."""
        result = check_publish_gate(
            public_record_authority="official_court_record",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert isinstance(result, RuleViolation)
        assert result.rule == "publish_gate_authority"

    def test_official_statistics_with_flags_on_passes(self) -> None:
        result = check_publish_gate(
            public_record_authority="official_statistics",
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert result is None


# ---------------------------------------------------------------------------
# enforce_all — full pipeline
# ---------------------------------------------------------------------------


class TestEnforceAll:
    """enforce_all() composes all three rule checks in a single call."""

    def test_clean_path_returns_empty_list(self) -> None:
        """A fully compliant source + record produces no violations."""
        violations = enforce_all(
            url="https://opendata.saskatoon.ca/crime_2024.csv",
            allowed_domains_json=json.dumps(["opendata.saskatoon.ca"]),
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json=_creates("CrimeIncident"),
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        assert violations == []

    def test_news_context_crime_incident_produces_multiple_violations(self) -> None:
        """news_context + CrimeIncident fails both the record-type gate and the
        publish gate."""
        violations = enforce_all(
            url="https://www.saskatoonpolice.ca/news/1234",
            allowed_domains_json=json.dumps(
                ["saskatoonpolice.ca", "www.saskatoonpolice.ca"]
            ),
            record_type="CrimeIncident",
            public_record_authority="news_context",
            creates_json=_creates("ReviewItem"),
            auto_publish_enabled=False,
            public_publish_default=False,
        )
        assert len(violations) >= 2
        rules = {v.rule for v in violations}
        # Record-type gate fires (authority_record_type or creates_declaration)
        assert rules & {"authority_record_type", "creates_declaration"}
        # Publish gate fires
        assert "publish_gate_authority" in rules

    def test_domain_violation_included_in_enforcement(self) -> None:
        """Domain violations appear alongside authority/publish violations."""
        violations = enforce_all(
            url="https://external.bad.example.com/data.csv",
            allowed_domains_json=json.dumps(["opendata.saskatoon.ca"]),
            record_type="CrimeIncident",
            public_record_authority="official_open_data",
            creates_json=_creates("CrimeIncident"),
            auto_publish_enabled=False,
            public_publish_default=True,
        )
        rules = {v.rule for v in violations}
        assert "domain_allowlist" in rules
        assert "publish_gate_flag" in rules

    def test_official_legislation_review_item_no_record_type_violation(self) -> None:
        """official_legislation + ReviewItem passes the record-type gate.
        The publish gate still fires because legislation is not auto-publish eligible.
        """
        violations = enforce_all(
            url="https://laws-lois.justice.gc.ca/some-act",
            allowed_domains_json=json.dumps(["laws-lois.justice.gc.ca"]),
            record_type="ReviewItem",
            public_record_authority="official_legislation",
            creates_json=_creates("ReviewItem"),
            auto_publish_enabled=True,
            public_publish_default=True,
        )
        rules = {v.rule for v in violations}
        assert "authority_record_type" not in rules
        assert "domain_allowlist" not in rules
        assert "publish_gate_authority" in rules
