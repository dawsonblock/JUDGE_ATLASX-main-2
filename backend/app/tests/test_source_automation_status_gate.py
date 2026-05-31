"""Tests for automation_status gate enforcement.

Covers:
- check_ingestion_allowed() in source_registry_ctl
- enable_source() / disable_source() endpoints in admin_sources
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.automation_statuses import (
    ADAPTER_MISSING,
    ALL_AUTOMATION_STATUSES,
    DISABLED_STUB,
    ENABLEABLE_STATUSES,
    MACHINE_READY_DISABLED,
    MACHINE_READY_ENABLED,
    MANUAL_ONLY,
    PARSER_MISSING,
    PORTAL_ONLY,
    QUARANTINED_SOURCE,
    RUNNABLE_STATUSES,
)
from app.ingestion.source_registry_ctl import check_ingestion_allowed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*, is_active: bool, automation_status: str | None) -> MagicMock:
    r = MagicMock()
    r.is_active = is_active
    r.automation_status = automation_status
    r.source_key = "test_source"
    return r


# ---------------------------------------------------------------------------
# check_ingestion_allowed() tests
# ---------------------------------------------------------------------------


def test_machine_ready_enabled_can_run() -> None:
    registry = _make_registry(is_active=True, automation_status=MACHINE_READY_ENABLED)
    allowed, reason = check_ingestion_allowed(registry)
    assert allowed is True
    assert reason == "ok"


def test_machine_ready_disabled_active_cannot_run() -> None:
    """MACHINE_READY_DISABLED must not run until explicitly enabled."""
    registry = _make_registry(is_active=True, automation_status=MACHINE_READY_DISABLED)
    allowed, reason = check_ingestion_allowed(registry)
    assert allowed is False
    assert MACHINE_READY_DISABLED in reason


def test_is_active_false_blocks_regardless_of_automation_status() -> None:
    registry = _make_registry(is_active=False, automation_status=MACHINE_READY_ENABLED)
    allowed, reason = check_ingestion_allowed(registry)
    assert allowed is False
    assert "disabled" in reason.lower()


@pytest.mark.parametrize(
    "status",
    [
        ADAPTER_MISSING,
        PARSER_MISSING,
        PORTAL_ONLY,
        MANUAL_ONLY,
        DISABLED_STUB,
        QUARANTINED_SOURCE,
    ],
)
def test_non_runnable_status_blocks_ingestion(status: str) -> None:
    registry = _make_registry(is_active=True, automation_status=status)
    allowed, reason = check_ingestion_allowed(registry)
    assert allowed is False
    assert status in reason


def test_none_automation_status_blocks_ingestion() -> None:
    registry = _make_registry(is_active=True, automation_status=None)
    allowed, reason = check_ingestion_allowed(registry)
    assert allowed is False
    assert "no automation_status" in reason


# ---------------------------------------------------------------------------
# automation_statuses module constants
# ---------------------------------------------------------------------------


def test_enableable_statuses_subset_of_all() -> None:
    assert ENABLEABLE_STATUSES <= ALL_AUTOMATION_STATUSES


def test_runnable_statuses_subset_of_all() -> None:
    assert RUNNABLE_STATUSES <= ALL_AUTOMATION_STATUSES


def test_machine_ready_disabled_is_only_enableable() -> None:
    assert ENABLEABLE_STATUSES == frozenset({MACHINE_READY_DISABLED})
