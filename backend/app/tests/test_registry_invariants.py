"""Invariant tests for YAML source registry entries.

Loads every *.yaml inside backend/app/ingestion/sources/ and asserts
structural contracts that must hold for every source entry.

These are NOT database tests — they operate purely on the YAML files so
they run in any environment (CI, local, no DB required).
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

_SOURCES_DIR = pathlib.Path(__file__).resolve().parent.parent / "ingestion" / "sources"

# Canonical set of allowed source_class values.
_VALID_SOURCE_CLASSES: frozenset[str] = frozenset(
    {
        "machine_ingest",
        "portal_reference",
        "disabled_stub",
        "manual_reference",
        "requires_api_key",
        "needs_endpoint_configuration",
    }
)


def _load_all_sources() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(_SOURCES_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        rows.extend(doc.get("sources", []) if isinstance(doc, dict) else [])
    return rows


class TestRegistryInvariants:
    """Structural-contract tests for the YAML source registry."""

    # ------------------------------------------------------------------
    # Sanity checks
    # ------------------------------------------------------------------

    def test_yaml_files_exist(self) -> None:
        """At least one YAML file must exist in the sources directory."""
        found = list(_SOURCES_DIR.glob("*.yaml"))
        assert len(found) >= 1, f"No *.yaml files found under {_SOURCES_DIR}"

    def test_sources_list_is_non_empty(self) -> None:
        """The combined sources list must contain at least one entry."""
        rows = _load_all_sources()
        assert len(rows) >= 1, "sources list parsed as empty"

    # ------------------------------------------------------------------
    # source_key invariants
    # ------------------------------------------------------------------

    def test_every_source_has_source_key(self) -> None:
        """Every source entry must have a non-empty source_key."""
        violations = [s for s in _load_all_sources() if not s.get("source_key")]
        assert violations == [], f"Sources missing source_key: {violations}"

    def test_source_keys_are_unique(self) -> None:
        """source_key values must be globally unique across all YAML files."""
        seen: list[str] = []
        duplicates: list[str] = []
        for src in _load_all_sources():
            key = src.get("source_key", "")
            if key in seen:
                duplicates.append(key)
            else:
                seen.append(key)
        assert duplicates == [], f"Duplicate source_key values: {duplicates}"

    # ------------------------------------------------------------------
    # source_class invariants
    # ------------------------------------------------------------------

    def test_all_source_classes_are_in_canonical_set(self) -> None:
        """Every source_class value must be one of the six canonical strings."""
        violations = [
            (s.get("source_key"), s.get("source_class"))
            for s in _load_all_sources()
            if s.get("source_class") not in _VALID_SOURCE_CLASSES
        ]
        assert violations == [], (
            f"Sources with invalid source_class: {violations}\n"
            f"Allowed values: {sorted(_VALID_SOURCE_CLASSES)}"
        )

    def test_every_machine_ingest_has_parser(self) -> None:
        """Every machine_ingest source must declare a non-empty parser key."""
        violations = [
            s.get("source_key")
            for s in _load_all_sources()
            if s.get("source_class") == "machine_ingest" and not s.get("parser")
        ]
        assert violations == [], f"machine_ingest sources missing parser: {violations}"

    def test_every_disabled_stub_has_admin_notes(self) -> None:
        """Every disabled_stub source must include admin_notes explaining the block."""
        violations = [
            s.get("source_key")
            for s in _load_all_sources()
            if s.get("source_class") == "disabled_stub" and not s.get("admin_notes")
        ]
        assert (
            violations == []
        ), f"disabled_stub sources missing admin_notes: {violations}"

    # ------------------------------------------------------------------
    # Safety flag invariants
    # ------------------------------------------------------------------

    def test_no_source_is_enabled_by_default(self) -> None:
        """enabled_default must be false (or absent) for every source.

        Sources require explicit admin activation; none may be on-by-default
        in the registry YAML.
        """
        violations = [
            s.get("source_key")
            for s in _load_all_sources()
            if s.get("enabled_default") is True
        ]
        assert violations == [], f"Sources with enabled_default=true: {violations}"

    def test_portal_reference_cannot_auto_publish(self) -> None:
        """portal_reference sources must not have auto_publish_enabled=true.

        Portal-reference sources require a completed adapter and explicit
        reclassification to machine_ingest before data may flow automatically.
        """
        violations = [
            s.get("source_key")
            for s in _load_all_sources()
            if s.get("source_class") == "portal_reference"
            and s.get("auto_publish_enabled") is True
        ]
        assert (
            violations == []
        ), f"portal_reference sources with auto_publish_enabled=true: {violations}"

    def test_disabled_stub_cannot_auto_publish(self) -> None:
        """disabled_stub sources must not have auto_publish_enabled=true."""
        violations = [
            s.get("source_key")
            for s in _load_all_sources()
            if s.get("source_class") == "disabled_stub"
            and s.get("auto_publish_enabled") is True
        ]
        assert (
            violations == []
        ), f"disabled_stub sources with auto_publish_enabled=true: {violations}"
