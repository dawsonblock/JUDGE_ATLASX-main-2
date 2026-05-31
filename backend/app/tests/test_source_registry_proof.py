"""Proof tests for the source registry verifier script.

Loads ``scripts/verify_source_registry.py`` via importlib (no subprocess)
and asserts the canonical invariants that must hold for every release:

1. ``verify()`` returns ``source_registry_ok: True`` against the real YAML.
2. ``generated_at`` is present and parseable as an ISO-8601 datetime.
3. ``violations`` is an empty list on a clean registry.
4. ``total_sources`` is a positive integer.
5. ``status_counts`` contains at least one key.
6. ``registry_summary`` length matches ``total_sources``.
7. Every registry_summary entry has ``source_key``, ``automation_status``,
   and ``in_registry`` fields.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "verify_source_registry.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("verify_source_registry", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, (
        f"Could not create module spec from {SCRIPT_PATH}"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSourceRegistryProof:
    """Proof invariants for the source registry verifier."""

    def test_script_path_exists(self) -> None:
        """The verifier script must exist at the expected path."""
        assert SCRIPT_PATH.exists(), f"verify_source_registry.py not found at {SCRIPT_PATH}"

    def test_verify_returns_source_registry_ok_true(self) -> None:
        """Current YAML must produce source_registry_ok=True (no violations)."""
        module = _load_module()
        result = module.verify()
        violations = result.get("violations", [])
        assert result["source_registry_ok"] is True, (
            f"source_registry_ok is False; violations: {violations}"
        )

    def test_generated_at_is_iso_datetime(self) -> None:
        """generated_at must be a parseable ISO-8601 UTC datetime string."""
        module = _load_module()
        result = module.verify()
        generated_at = result.get("generated_at")
        assert generated_at is not None, "generated_at is missing from verify() output"
        # Must parse without raising
        dt = datetime.fromisoformat(generated_at)
        assert dt.tzinfo is not None, "generated_at must include timezone info"

    def test_violations_is_empty_list(self) -> None:
        """violations must be an empty list on a clean registry."""
        module = _load_module()
        result = module.verify()
        assert result["violations"] == [], (
            f"Expected no violations; got: {result['violations']}"
        )

    def test_total_sources_is_positive(self) -> None:
        """total_sources must be > 0."""
        module = _load_module()
        result = module.verify()
        assert result["total_sources"] > 0, "total_sources must be a positive integer"

    def test_status_counts_has_entries(self) -> None:
        """status_counts must contain at least one automation_status key."""
        module = _load_module()
        result = module.verify()
        assert isinstance(result.get("status_counts"), dict), "status_counts must be a dict"
        assert len(result["status_counts"]) >= 1, "status_counts must have at least one entry"

    def test_registry_summary_length_matches_total(self) -> None:
        """registry_summary length must equal total_sources."""
        module = _load_module()
        result = module.verify()
        assert len(result["registry_summary"]) == result["total_sources"], (
            "registry_summary length must match total_sources"
        )

    def test_registry_summary_entries_have_required_fields(self) -> None:
        """Every registry_summary entry must have source_key, automation_status, in_registry."""
        module = _load_module()
        result = module.verify()
        for entry in result["registry_summary"]:
            assert "source_key" in entry, f"Missing source_key in entry: {entry}"
            assert "automation_status" in entry, f"Missing automation_status in entry: {entry}"
            assert "in_registry" in entry, f"Missing in_registry in entry: {entry}"
            assert "violations" in entry, f"Missing violations list in entry: {entry}"

    def test_stale_artifacts_empty_when_ok(self) -> None:
        """stale_artifacts must be empty when source_registry_ok is True."""
        module = _load_module()
        result = module.verify()
        if result["source_registry_ok"]:
            assert result.get("stale_artifacts", []) == [], (
                "stale_artifacts must be empty when source_registry_ok is True"
            )

    def test_machine_ready_enabled_status_in_counts(self) -> None:
        """At least one source with machine_ready_enabled must exist in registry."""
        module = _load_module()
        result = module.verify()
        counts = result["status_counts"]
        assert "machine_ready_enabled" in counts, (
            "Expected at least one machine_ready_enabled source in registry; "
            f"got status_counts: {counts}"
        )
