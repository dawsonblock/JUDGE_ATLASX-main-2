"""Tests for canada_saskatchewan_sources.yaml and SourceRegistry seeding.

Verifies that the YAML file can be loaded, all 16 sources are present,
required safety defaults are set, and the seed/repair logic merges
YAML sources with the hard-coded list correctly.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

_YAML_PATH = (
    pathlib.Path(__file__).parent.parent
    / "ingestion"
    / "sources"
    / "canada_saskatchewan_sources.yaml"
)

_EXPECTED_SOURCE_KEYS = {
    "saskatoon_open_data_crime",
    "saskatoon_police_open_data",
    "web_monitor_saskatoon_police_news",
    "sk_courts_qb_decisions",
    "sk_courts_ca_decisions",
    "statscan_ccjs_crime_sk",
    "statscan_ucr_national",
    "canlii_sk",
    "federal_court_canada",
    "scc_decisions",
    "sk_justice_ministry",
    "sk_legislature_hansard",
    "canada_open_data_crime",
    "rcmp_sk_news",
    "justice_canada_laws_xml",
    "saskatoon_open_data_portal",
}


def _load_yaml() -> list[dict]:
    with _YAML_PATH.open() as fh:
        data = yaml.safe_load(fh)
    return data.get("sources", [])


def test_yaml_file_exists() -> None:
    assert _YAML_PATH.exists(), f"YAML not found at {_YAML_PATH}"


def test_yaml_parses_without_error() -> None:
    sources = _load_yaml()
    assert isinstance(sources, list)
    assert len(sources) > 0


def test_yaml_contains_all_16_sources() -> None:
    sources = _load_yaml()
    keys = {s["source_key"] for s in sources}
    missing = _EXPECTED_SOURCE_KEYS - keys
    assert not missing, f"Missing source keys: {missing}"


def test_all_sources_disabled_by_default() -> None:
    """No source should be auto-enabled — manual review gate is required."""
    sources = _load_yaml()
    for s in sources:
        assert (
            s.get("enabled_default") is False
        ), f"Source '{s['source_key']}' has enabled_default=True but must be False"


def test_all_sources_require_manual_review() -> None:
    sources = _load_yaml()
    for s in sources:
        assert (
            s.get("requires_manual_review") is True
        ), f"Source '{s['source_key']}' does not have requires_manual_review=True"


def test_all_sources_no_auto_publish() -> None:
    sources = _load_yaml()
    for s in sources:
        assert (
            s.get("auto_publish_enabled") is False
        ), f"Source '{s['source_key']}' has auto_publish_enabled=True but must be False"


def test_allowed_domains_is_valid_json_or_list() -> None:
    """allowed_domains must be a list (YAML) or valid JSON array string."""
    sources = _load_yaml()
    for s in sources:
        domains = s.get("allowed_domains")
        if domains is None:
            continue
        if isinstance(domains, list):
            continue  # YAML list — fine
        # If it's a string it must be a valid JSON array
        parsed = json.loads(domains)
        assert isinstance(
            parsed, list
        ), f"Source '{s['source_key']}' allowed_domains is not a list: {domains}"


def test_creates_is_valid_list() -> None:
    sources = _load_yaml()
    for s in sources:
        creates = s.get("creates")
        if creates is None:
            continue
        if isinstance(creates, list):
            continue
        parsed = json.loads(creates)
        assert isinstance(parsed, list)


def test_news_sources_only_create_review_items() -> None:
    """Sources with news_context authority must not claim to create CrimeIncident."""
    sources = _load_yaml()
    for s in sources:
        if s.get("public_record_authority") == "news_context":
            creates = s.get("creates", [])
            if isinstance(creates, str):
                creates = json.loads(creates)
            assert (
                "CrimeIncident" not in creates
            ), f"news_context source '{s['source_key']}' claims to create CrimeIncident"


def test_parser_keys_are_known() -> None:
    from app.ingestion.source_adapters import ADAPTER_REGISTRY

    sources = _load_yaml()
    for s in sources:
        parser = s.get("parser")
        if parser:
            assert (
                parser in ADAPTER_REGISTRY
            ), f"Source '{s['source_key']}' references unknown parser '{parser}'"


def test_saskatchewan_court_sources_enablement_readiness() -> None:
    """Phase 8: Verify Saskatchewan court sources are ready for enablement."""
    from app.seed.source_registry import validate_machine_ingest_source_spec

    sources = _load_yaml()
    sk_court_sources = {
        s["source_key"]: s
        for s in sources
        if s["source_key"] in ["sk_courts_qb_decisions", "sk_courts_ca_decisions"]
    }

    # Verify both Saskatchewan court sources exist
    assert "sk_courts_qb_decisions" in sk_court_sources
    assert "sk_courts_ca_decisions" in sk_court_sources

    # Verify both sources pass machine_ingest validation
    for source_key, spec in sk_court_sources.items():
        violations = validate_machine_ingest_source_spec(spec)
        assert not violations, f"{source_key} has violations: {violations}"

    # Verify sk_courts_qb_decisions is disabled by default but runnable
    qb_source = sk_court_sources["sk_courts_qb_decisions"]
    assert qb_source["enabled_default"] is False
    assert qb_source["lifecycle_state"] == "runnable_disabled"
    assert qb_source["automation_status"] == "machine_ready_disabled"

    # Verify sk_courts_ca_decisions is disabled but runnable
    ca_source = sk_court_sources["sk_courts_ca_decisions"]
    assert ca_source["enabled_default"] is False
    assert ca_source["lifecycle_state"] == "runnable_disabled"
    assert ca_source["automation_status"] == "machine_ready_disabled"

    # Verify both sources use CanLII API
    assert qb_source["parser"] == "canlii_api"
    assert ca_source["parser"] == "canlii_api"

    # Verify both sources require authentication
    assert qb_source["authentication_required"] is True
    assert ca_source["authentication_required"] is True

    # Verify both sources have evidence required
    assert qb_source["evidence_required"] is True
    assert ca_source["evidence_required"] is True

    # Verify both sources have terms verified
    assert qb_source["terms_verified"] == "2026-05-06"
    assert ca_source["terms_verified"] == "2026-05-06"

    # Verify both sources have proper rate limit policy
    assert qb_source["rate_limit_policy"] == "api_key_required"
    assert ca_source["rate_limit_policy"] == "api_key_required"

    # Verify both sources have proper confidence class
    assert qb_source["confidence_class"] == "primary_official"
    assert ca_source["confidence_class"] == "primary_official"

    # Verify both sources have proper retention policy
    assert qb_source["retention_policy"] == "indefinite"
    assert ca_source["retention_policy"] == "indefinite"
