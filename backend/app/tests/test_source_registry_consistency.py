"""Source registry YAML consistency tests.

Pins the canonical truth about individual sources so that stale docs or
accidental YAML edits cannot go undetected.  These tests act as a
"canary" — if a field drifts they fail before any generated artifact
can propagate a wrong value.

Invariants enforced:
- justice_canada_laws_xml has automation_status=machine_ready_enabled
  and lifecycle_state=runnable (regression guard after Phase-3 fix).
- All machine_ingest sources with automation_status=machine_ready_enabled
  must also have lifecycle_state=runnable.
- All disabled_stub sources have enabled_default=False and
  automation_status=disabled_stub.
- No source has both public_publish_default=True and
  requires_manual_review=False (would bypass the editorial gate).
- parser_version is present on every machine_ingest source.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

_YAML_PATH = (
    pathlib.Path(__file__).parent.parent
    / "ingestion"
    / "sources"
    / "canada_saskatchewan_sources.yaml"
)


def _load_sources() -> list[dict]:
    with _YAML_PATH.open() as fh:
        data = yaml.safe_load(fh)
    return data.get("sources", [])


def _by_key(sources: list[dict]) -> dict[str, dict]:
    return {s["source_key"]: s for s in sources}


# ---------------------------------------------------------------------------
# Regression guard: justice_canada_laws_xml canonical values
# ---------------------------------------------------------------------------


class TestJusticeCanadaCanonical:
    """Pin the truth for justice_canada_laws_xml after the Phase-3 correction."""

    def test_automation_status_is_machine_ready_enabled(self) -> None:
        sources = _by_key(_load_sources())
        entry = sources.get("justice_canada_laws_xml")
        assert entry is not None, "justice_canada_laws_xml must be present in YAML"
        assert entry.get("automation_status") == "machine_ready_enabled", (
            "justice_canada_laws_xml automation_status drifted from machine_ready_enabled; "
            "update tests only after deliberate YAML change and doc regeneration."
        )

    def test_lifecycle_state_is_runnable(self) -> None:
        sources = _by_key(_load_sources())
        entry = sources.get("justice_canada_laws_xml")
        assert entry is not None, "justice_canada_laws_xml must be present in YAML"
        assert entry.get("lifecycle_state") == "runnable", (
            "justice_canada_laws_xml lifecycle_state drifted from runnable"
        )

    def test_source_class_is_machine_ingest(self) -> None:
        sources = _by_key(_load_sources())
        entry = sources.get("justice_canada_laws_xml")
        assert entry is not None
        assert entry.get("source_class") == "machine_ingest"

    def test_parser_is_laws_justice_xml(self) -> None:
        sources = _by_key(_load_sources())
        entry = sources.get("justice_canada_laws_xml")
        assert entry is not None
        assert entry.get("parser") == "laws_justice_xml"


# ---------------------------------------------------------------------------
# Cross-field consistency: machine_ready_enabled implies runnable
# ---------------------------------------------------------------------------


def test_machine_ready_enabled_sources_have_lifecycle_runnable() -> None:
    """Any machine_ready_enabled source must declare lifecycle_state=runnable."""
    sources = _load_sources()
    bad = [
        s["source_key"]
        for s in sources
        if s.get("automation_status") == "machine_ready_enabled"
        and s.get("lifecycle_state") != "runnable"
    ]
    assert not bad, (
        f"These sources have automation_status=machine_ready_enabled but "
        f"lifecycle_state != runnable: {bad}"
    )


# ---------------------------------------------------------------------------
# disabled_stub invariants
# ---------------------------------------------------------------------------


def test_disabled_stub_sources_have_enabled_default_false() -> None:
    sources = _load_sources()
    bad = [
        s["source_key"]
        for s in sources
        if s.get("automation_status") == "disabled_stub"
        and s.get("enabled_default") is not False
    ]
    assert not bad, (
        f"disabled_stub sources must have enabled_default=False: {bad}"
    )


# ---------------------------------------------------------------------------
# Editorial gate: no source can auto-publish without manual review
# ---------------------------------------------------------------------------


def test_no_source_bypasses_editorial_gate() -> None:
    """public_publish_default=True + requires_manual_review=False is forbidden."""
    sources = _load_sources()
    bad = [
        s["source_key"]
        for s in sources
        if s.get("public_publish_default") is True
        and s.get("requires_manual_review") is not True
    ]
    assert not bad, (
        f"These sources allow auto-publish without manual review (editorial gate bypass): {bad}"
    )


# ---------------------------------------------------------------------------
# machine_ingest parser_version presence
# ---------------------------------------------------------------------------


def test_machine_ingest_sources_have_parser_version() -> None:
    sources = _load_sources()
    bad = [
        s["source_key"]
        for s in sources
        if s.get("source_class") == "machine_ingest"
        and not s.get("parser_version")
    ]
    assert not bad, (
        f"machine_ingest sources missing parser_version: {bad}"
    )


def test_statscan_sources_remain_portal_reference_aggregate_only() -> None:
    """StatsCan entries must remain non-runnable portal references in this phase."""
    sources = _by_key(_load_sources())
    for key in ("statscan_ccjs_crime_sk", "statscan_ucr_national"):
        entry = sources.get(key)
        assert entry is not None, f"missing source entry: {key}"
        assert entry.get("source_type") == "aggregate_stats"
        assert entry.get("source_class") == "portal_reference"
        assert entry.get("automation_status") == "adapter_missing"
        assert entry.get("enabled_default") is False
        assert entry.get("requires_manual_review") is True
        assert entry.get("public_publish_default") is True
