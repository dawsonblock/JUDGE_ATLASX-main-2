"""Tests for canonical ingestion run status constants (Phase 5).

All tests are pure-Python — no database, no network.
"""

from __future__ import annotations

import pytest

from app.ingestion.statuses import (
    ALL_STATUSES,
    CANCELLED,
    COMPLETED,
    COMPLETED_WITH_ERRORS,
    COMPLETED_WITH_WARNINGS,
    FAILED,
    PENDING,
    QUARANTINED,
    RUNNING,
    TERMINAL_STATUSES,
    normalize_status,
)

# ---------------------------------------------------------------------------
# Canonical values have the correct string representations
# ---------------------------------------------------------------------------


def test_status_string_values():
    assert PENDING == "pending"
    assert RUNNING == "running"
    assert COMPLETED == "completed"
    assert COMPLETED_WITH_ERRORS == "completed_with_errors"
    assert FAILED == "failed"
    assert CANCELLED == "cancelled"
    assert QUARANTINED == "quarantined"


# ---------------------------------------------------------------------------
# ALL_STATUSES contains every individual constant
# ---------------------------------------------------------------------------


def test_all_statuses_membership():
    for status in (
        PENDING,
        RUNNING,
        COMPLETED,
        COMPLETED_WITH_WARNINGS,
        FAILED,
        CANCELLED,
        QUARANTINED,
    ):
        assert status in ALL_STATUSES


def test_completed_with_errors_not_in_all_statuses():
    """COMPLETED_WITH_ERRORS is deprecated and must not appear in the active set."""
    assert COMPLETED_WITH_ERRORS not in ALL_STATUSES


# ---------------------------------------------------------------------------
# TERMINAL_STATUSES is a strict subset of ALL_STATUSES and excludes active ones
# ---------------------------------------------------------------------------


def test_terminal_statuses_subset():
    assert TERMINAL_STATUSES <= ALL_STATUSES


def test_terminal_statuses_excludes_active():
    assert PENDING not in TERMINAL_STATUSES
    assert RUNNING not in TERMINAL_STATUSES


def test_terminal_statuses_includes_completed_variants():
    assert COMPLETED in TERMINAL_STATUSES
    assert COMPLETED_WITH_WARNINGS in TERMINAL_STATUSES
    assert COMPLETED_WITH_ERRORS not in TERMINAL_STATUSES
    assert FAILED in TERMINAL_STATUSES
    assert CANCELLED in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# normalize_status maps legacy aliases to canonical values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "legacy,expected",
    [
        ("complete", COMPLETED),
        ("partial", COMPLETED_WITH_WARNINGS),
        ("success", COMPLETED),
        ("error", FAILED),
    ],
)
def test_normalize_status_legacy_aliases(legacy: str, expected: str):
    assert normalize_status(legacy) == expected


def test_normalize_status_canonical_passthrough():
    for status in ALL_STATUSES:
        assert normalize_status(status) == status


def test_normalize_status_unknown_passthrough():
    assert normalize_status("some_unknown_value") == "some_unknown_value"


# ---------------------------------------------------------------------------
# Legacy values ("complete", "partial", etc.) are NOT in ALL_STATUSES
# ---------------------------------------------------------------------------


def test_legacy_values_not_in_all_statuses():
    for legacy in ("complete", "partial", "success", "error"):
        assert (
            legacy not in ALL_STATUSES
        ), f"Legacy value {legacy!r} must not appear in ALL_STATUSES"
