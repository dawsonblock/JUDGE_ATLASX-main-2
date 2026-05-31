"""Tests for parser_version contract enforcement in _validate_machine_ingest_contract.

Phase 4 added version-mismatch detection so quarantine is triggered when
  - source.parser_version is set but result.parser_version is None
  - both are set but they don't match
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ingestion.source_runner import _validate_machine_ingest_contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    raw_bytes: bytes = b"content",
    fetch_url: str = "https://example.com",
    parser_version: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.raw_snapshot_bytes = raw_bytes
    r.fetch_url = fetch_url
    r.parser_version = parser_version
    return r


def _make_source(
    *,
    parser_version: str | None = None,
    base_url: str = "https://example.com",
) -> MagicMock:
    s = MagicMock()
    s.parser_version = parser_version
    s.base_url = base_url
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_source_parser_version_is_violation() -> None:
    result = _make_result(parser_version="1.0")
    source = _make_source(parser_version=None)
    violations = _validate_machine_ingest_contract(result, source)
    assert "no_parser_version" in violations


def test_source_has_version_result_missing_is_violation() -> None:
    """Adapter did not report back parser_version → quarantine."""
    result = _make_result(parser_version=None)
    source = _make_source(parser_version="1.0")
    violations = _validate_machine_ingest_contract(result, source)
    assert "no_parser_version" in violations


def test_parser_version_mismatch_is_violation() -> None:
    result = _make_result(parser_version="2.0")
    source = _make_source(parser_version="1.0")
    violations = _validate_machine_ingest_contract(result, source)
    assert "parser_version_mismatch" in violations
    assert "no_parser_version" not in violations


def test_matching_parser_version_passes() -> None:
    result = _make_result(parser_version="1.0")
    source = _make_source(parser_version="1.0")
    violations = _validate_machine_ingest_contract(result, source)
    assert "no_parser_version" not in violations
    assert "parser_version_mismatch" not in violations


def test_only_version_violation_when_other_fields_ok() -> None:
    result = _make_result(raw_bytes=b"x", fetch_url="https://x.com", parser_version="2.0")
    source = _make_source(parser_version="1.0")
    violations = _validate_machine_ingest_contract(result, source)
    assert violations == ["parser_version_mismatch"]
