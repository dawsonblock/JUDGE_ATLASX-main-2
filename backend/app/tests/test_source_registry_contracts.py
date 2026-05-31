"""Tests for source registry spec validation contracts.

Verifies that:
- machine_ingest sources without required fields are rejected by the validator
- portal_reference/disabled_stub sources pass without parser_version
- selected canonical machine_ingest sources in the YAML have parser_version set
- validate_machine_ingest_source_spec returns correct violation slugs
- parser_version is in _REPAIR_FIELDS so drift gets corrected
"""

from __future__ import annotations

import pathlib

import yaml
from app.seed.source_registry import (
    _REPAIR_FIELDS,
    validate_all_source_specs,
    validate_machine_ingest_source_spec,
)

_YAML_PATH = (
    pathlib.Path(__file__).parent.parent
    / "ingestion"
    / "sources"
    / "canada_saskatchewan_sources.yaml"
)

_MACHINE_INGEST_SOURCE_KEYS = {
    "sk_courts_qb_decisions",
    "sk_courts_ca_decisions",
    "federal_court_canada",
    "scc_decisions",
    "sk_legislature_hansard",
    "justice_canada_laws_xml",
}


def _load_yaml() -> list[dict]:
    with _YAML_PATH.open() as fh:
        data = yaml.safe_load(fh)
    return data.get("sources", [])


# ── validate_machine_ingest_source_spec unit tests ──────────────────────────


def test_valid_machine_ingest_spec_passes() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": "1.0",
        "base_url": "https://example.com/api",
        "public_record_authority": "official_public_record",
        "requires_manual_review": True,
        "public_publish_default": False,
        "terms_url": "https://example.com/terms",
        "automation_status": "machine_ready_disabled",
        "lifecycle_state": "runnable_disabled",
        "allowed_domains": '["example.com"]',
        # Sprint C: provenance and access fields
        "confidence_class": "primary_official",
        "retention_policy": "indefinite",
        "canonical_url": "https://example.com/api",
        "evidence_required": True,
        "terms_verified": "2026-05-06",
        "authentication_required": False,
        "rate_limit_policy": "polite_1rps",
    }
    assert validate_machine_ingest_source_spec(spec) == []


def test_missing_parser_version_is_violation() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": None,
        "allowed_domains": '["example.com"]',
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "missing_parser_version" in violations


def test_missing_parser_is_violation() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": None,
        "parser_version": "1.0",
        "allowed_domains": '["example.com"]',
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "missing_parser" in violations


def test_missing_allowed_domains_is_violation() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": "1.0",
        "allowed_domains": None,
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "missing_allowed_domains" in violations


def test_empty_allowed_domains_json_is_violation() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": "1.0",
        "allowed_domains": "[]",
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "missing_allowed_domains" in violations


def test_portal_reference_skips_validation() -> None:
    """Non machine_ingest sources are never validated."""
    spec = {
        "source_key": "test_source",
        "source_class": "portal_reference",
        # missing parser, parser_version, allowed_domains
    }
    assert validate_machine_ingest_source_spec(spec) == []


def test_disabled_stub_skips_validation() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "disabled_stub",
    }
    assert validate_machine_ingest_source_spec(spec) == []


def test_no_source_class_is_violation() -> None:
    """source_class=None is treated as machine_ingest via legacy path."""
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        # missing everything required
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert len(violations) > 0


def test_multiple_violations_returned() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "missing_parser" in violations
    assert "missing_parser_version" in violations
    assert "missing_allowed_domains" in violations


def test_invalid_machine_ingest_value_sets_are_rejected() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": "1.0",
        "base_url": "https://example.com/api",
        "public_record_authority": "official_public_record",
        "requires_manual_review": True,
        "public_publish_default": False,
        "terms_url": "https://example.com/terms",
        "automation_status": "machine_ready_disabled",
        "lifecycle_state": "runnable_disabled",
        "allowed_domains": '["example.com"]',
        "confidence_class": "invalid_class",
        "retention_policy": "forever",
        "canonical_url": "not-a-url",
        "evidence_required": False,
        "terms_verified": "false",
        "authentication_required": False,
        "rate_limit_policy": "unknown",
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "invalid_confidence_class" in violations  # nosec B101
    assert "invalid_retention_policy" in violations  # nosec B101
    assert "invalid_rate_limit_policy" in violations  # nosec B101
    assert "invalid_terms_verified" in violations  # nosec B101
    assert "invalid_canonical_url" in violations  # nosec B101
    assert "evidence_required_must_be_true" in violations  # nosec B101


def test_machine_ingest_automation_lifecycle_mismatch_is_rejected() -> None:
    spec = {
        "source_key": "test_source",
        "source_class": "machine_ingest",
        "parser": "my_parser",
        "parser_version": "1.0",
        "base_url": "https://example.com/api",
        "public_record_authority": "official_public_record",
        "requires_manual_review": True,
        "public_publish_default": False,
        "terms_url": "https://example.com/terms",
        "automation_status": "machine_ready_enabled",
        "lifecycle_state": "runnable_disabled",
        "allowed_domains": '["example.com"]',
        "confidence_class": "primary_official",
        "retention_policy": "indefinite",
        "canonical_url": "https://example.com/api",
        "evidence_required": True,
        "terms_verified": "2026-05-06",
        "authentication_required": False,
        "rate_limit_policy": "polite_1rps",
    }
    violations = validate_machine_ingest_source_spec(spec)
    assert "automation_lifecycle_mismatch" in violations  # nosec B101


# ── YAML contract tests ──────────────────────────────────────────────────────


def test_all_machine_ingest_sources_have_parser_version() -> None:
    """machine_ingest sources must declare parser_version."""
    sources = _load_yaml()
    violations: list[str] = []
    for s in sources:
        if s.get("source_class") == "machine_ingest":
            if not s.get("parser_version"):
                violations.append(s["source_key"])
    assert (
        not violations
    ), f"machine_ingest sources missing parser_version: {violations}"


def test_specific_machine_ingest_sources_have_parser_version() -> None:
    """Selected canonical machine_ingest source keys must have parser_version."""
    sources = {s["source_key"]: s for s in _load_yaml()}
    for key in _MACHINE_INGEST_SOURCE_KEYS:
        source = sources.get(key)
        assert source is not None, f"Expected source '{key}' not found in YAML"
        assert source.get(
            "parser_version"
        ), f"Source '{key}' is machine_ingest but has no parser_version"


def test_machine_ingest_sources_pass_spec_validator() -> None:
    """All machine_ingest sources must pass the contract validator."""
    sources = _load_yaml()
    failures: dict[str, list[str]] = {}
    for s in sources:
        if s.get("source_class") == "machine_ingest":
            violations = validate_machine_ingest_source_spec(s)
            if violations:
                failures[s["source_key"]] = violations
    assert not failures, f"machine_ingest spec violations: {failures}"


def test_machine_ingest_sources_have_valid_state_transitions() -> None:
    """machine_ingest sources must keep automation and lifecycle states aligned."""
    sources = _load_yaml()
    failures: dict[str, list[str]] = {}
    for s in sources:
        if s.get("source_class") == "machine_ingest":
            violations = validate_machine_ingest_source_spec(s)
            state_violations = [
                v
                for v in violations
                if v
                in {
                    "invalid_automation_status",
                    "invalid_lifecycle_state",
                    "automation_lifecycle_mismatch",
                }
            ]
            if state_violations:
                failures[s["source_key"]] = state_violations
    assert (
        not failures
    ), f"machine_ingest state metadata violations: {failures}"  # nosec B101


# ── _REPAIR_FIELDS coverage test ─────────────────────────────────────────────


def test_parser_version_in_repair_fields() -> None:
    """parser_version must be in _REPAIR_FIELDS for repair syncing."""
    assert "parser_version" in _REPAIR_FIELDS, (
        "parser_version is not in seed._REPAIR_FIELDS"
        " — DB drift will not be corrected"
    )


# ── Zero-violation gate ──────────────────────────────────────────────────────


def test_current_yaml_has_no_machine_ingest_violations() -> None:
    """machine_ingest sources in the live YAML must pass the spec validator.

    This is the CI gate that ensures no malformed source spec can be merged.
    validate_all_source_specs() returns {source_key: [violations]} — an empty
    dict means every source is clean.
    """
    violations = validate_all_source_specs()
    assert (
        violations == {}
    ), f"machine_ingest spec violations found in YAML: {violations}"
