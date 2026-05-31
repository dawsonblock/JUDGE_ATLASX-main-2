"""Tests for Phase 4: machine_ingest pre-save contract validation.

The runner must quarantine any machine_ingest run that:
- provides no raw snapshot bytes
- has no resolvable source URL
- comes from a source with no parser_version declared

Portal-reference and other non-machine_ingest sources bypass this gate.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from app.ingestion.adapters import ContractViolationError, IngestionResult
from app.ingestion.source_runner import (
    RunPersistSummary,
    _MACHINE_INGEST_CLASSES,
    _validate_machine_ingest_contract,
    persist_ingestion_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    *,
    source_class: str | None = "machine_ingest",
    base_url: str | None = "https://example.gc.ca/",
    parser_version: str | None = "1.0",
    source_key: str = "test_source",
) -> MagicMock:
    src = MagicMock()
    src.source_class = source_class
    src.base_url = base_url
    src.parser_version = parser_version
    src.source_key = source_key
    src.creates = json.dumps(["SourceSnapshot", "CrimeIncident"])
    src.public_record_authority = "public_access"
    return src


def _make_run() -> MagicMock:
    run = MagicMock()
    run.id = 42
    run.persisted_count = 0
    run.skipped_count = 0
    return run


def _make_db() -> MagicMock:
    db = MagicMock()
    db.flush = MagicMock()
    return db


def _healthy_result(fetch_url: str = "https://example.gc.ca/data") -> IngestionResult:
    return IngestionResult(
        source_key="test_source",
        raw_snapshot_bytes=b"<html>some content</html>",
        fetch_url=fetch_url,
        fetch_http_status=200,
        fetch_content_type="text/html",
        parser_version="1.0",
    )


# ---------------------------------------------------------------------------
# Unit tests: _validate_machine_ingest_contract
# ---------------------------------------------------------------------------


class TestValidateMachineIngestContract:
    def test_valid_result_returns_no_violations(self) -> None:
        source = _make_source()
        result = _healthy_result()
        violations = _validate_machine_ingest_contract(result, source)
        assert violations == []

    def test_empty_bytes_returns_no_raw_content(self) -> None:
        source = _make_source()
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=b"",
            fetch_url="https://example.gc.ca/data",
        )
        violations = _validate_machine_ingest_contract(result, source)
        assert "no_raw_content" in violations

    def test_none_bytes_returns_no_raw_content(self) -> None:
        source = _make_source()
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=None,
            fetch_url="https://example.gc.ca/data",
        )
        violations = _validate_machine_ingest_contract(result, source)
        assert "no_raw_content" in violations

    def test_no_url_anywhere_returns_no_fetch_url(self) -> None:
        source = _make_source(base_url=None)
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=b"data",
            fetch_url=None,
        )
        violations = _validate_machine_ingest_contract(result, source)
        assert "no_fetch_url" in violations

    def test_base_url_satisfies_url_requirement(self) -> None:
        """source.base_url counts as a valid URL even if fetch_url is None."""
        source = _make_source(base_url="https://example.gc.ca/")
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=b"data",
            fetch_url=None,
        )
        violations = _validate_machine_ingest_contract(result, source)
        assert "no_fetch_url" not in violations

    def test_no_parser_version_returns_no_parser_version(self) -> None:
        source = _make_source(parser_version=None)
        result = _healthy_result()
        violations = _validate_machine_ingest_contract(result, source)
        assert "no_parser_version" in violations

    def test_multiple_violations_all_reported(self) -> None:
        """All three violations must be present when nothing is configured."""
        source = _make_source(base_url=None, parser_version=None)
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=None,
            fetch_url=None,
        )
        violations = _validate_machine_ingest_contract(result, source)
        assert set(violations) == {"no_raw_content", "no_fetch_url", "no_parser_version"}


# ---------------------------------------------------------------------------
# Integration tests: persist_ingestion_result quarantine path
# ---------------------------------------------------------------------------


class TestPersistIngestionResultQuarantine:
    def test_machine_ingest_with_no_bytes_quarantines_run(self) -> None:
        db = _make_db()
        source = _make_source()
        run = _make_run()
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=None,
            fetch_url="https://example.gc.ca/data",
        )

        with patch("app.ingestion.source_runner.quarantine_run") as mock_qr:
            summary = persist_ingestion_result(db, source, run, result)

        mock_qr.assert_called_once()
        reason_arg = mock_qr.call_args[0][2]  # third positional arg
        assert "no_raw_content" in reason_arg
        assert summary.persisted_incidents == 0
        assert summary.persisted_review_items == 0

    def test_machine_ingest_none_source_class_treated_as_machine_ingest(self) -> None:
        """Legacy sources with source_class=None must also be validated."""
        db = _make_db()
        source = _make_source(source_class=None)
        run = _make_run()
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=None,
            fetch_url=None,
        )

        with patch("app.ingestion.source_runner.quarantine_run") as mock_qr:
            persist_ingestion_result(db, source, run, result)

        mock_qr.assert_called_once()

    def test_portal_reference_skips_machine_ingest_validation(self) -> None:
        """portal_reference sources must NOT be quarantined by this gate."""
        db = _make_db()
        source = _make_source(
            source_class="portal_reference",
            base_url=None,
            parser_version=None,
        )
        run = _make_run()
        # portal_reference with no raw bytes — would fail machine_ingest gate
        result = IngestionResult(
            source_key="test_source",
            raw_snapshot_bytes=None,
            fetch_url=None,
        )

        with patch("app.ingestion.source_runner.quarantine_run") as mock_qr:
            with patch("app.ingestion.source_runner._create_snapshot") as mock_snap:
                persist_ingestion_result(db, source, run, result)

        mock_qr.assert_not_called()

    def test_valid_machine_ingest_proceeds_to_snapshot_creation(self) -> None:
        """A result that passes all checks must reach _create_snapshot."""
        db = _make_db()
        source = _make_source()
        run = _make_run()
        result = _healthy_result()  # only records metadata, no created_records

        with patch("app.ingestion.source_runner.quarantine_run") as mock_qr:
            with patch("app.ingestion.source_runner._create_snapshot") as mock_snap:
                mock_snap.return_value = MagicMock(id=1)
                persist_ingestion_result(db, source, run, result)

        mock_qr.assert_not_called()
        mock_snap.assert_called_once()


# ---------------------------------------------------------------------------
# Contract error class tests
# ---------------------------------------------------------------------------


class TestContractViolationError:
    def test_reason_attribute_stored(self) -> None:
        err = ContractViolationError("no_raw_content", "Adapter returned no bytes")
        assert err.reason == "no_raw_content"

    def test_default_message_falls_back_to_reason(self) -> None:
        err = ContractViolationError("no_parser_version")
        assert str(err) == "no_parser_version"

    def test_is_exception(self) -> None:
        assert issubclass(ContractViolationError, Exception)


# ---------------------------------------------------------------------------
# Adapter base class validate_record_contract hook
# ---------------------------------------------------------------------------


class TestValidateRecordContractHook:
    def test_default_implementation_does_not_raise(self) -> None:
        from app.ingestion.adapters import CanadianSourceAdapter

        class _ConcreteAdapter(CanadianSourceAdapter):
            def fetch(self) -> list:
                return []

            def parse(self, raw: list) -> list:
                return []

            def run(self) -> IngestionResult:
                return IngestionResult(source_key="test")

        adapter = _ConcreteAdapter()
        result = IngestionResult(source_key="test", raw_snapshot_bytes=b"data")
        # Should not raise — default is a safe no-op
        adapter.validate_record_contract(result)

    def test_subclass_can_raise_contract_violation_error(self) -> None:
        from app.ingestion.adapters import CanadianSourceAdapter

        class _StrictAdapter(CanadianSourceAdapter):
            def fetch(self) -> list:
                return []

            def parse(self, raw: list) -> list:
                return []

            def run(self) -> IngestionResult:
                return IngestionResult(source_key="test")

            def validate_record_contract(self, result: IngestionResult) -> None:
                if not result.raw_snapshot_bytes:
                    raise ContractViolationError("no_raw_content")

        adapter = _StrictAdapter()
        with pytest.raises(ContractViolationError, match="no_raw_content"):
            adapter.validate_record_contract(IngestionResult(source_key="test"))
