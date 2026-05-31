"""Tests for admin source run status truth — Phase 2 fix verification.

Guards that:
- When persist_ingestion_result quarantines a run, run_source_now does NOT
    overwrite the status with completed/completed_with_warnings (the core bug fixed
  in Phase 2).
- The RunResult return dict accurately reflects: success, status, pipeline_stage,
  snapshots_written, contract_violations, persisted_incidents,
  persisted_review_items, and duplicates_skipped.
- success is False when status is quarantined.
- success is True for completed and completed_with_warnings.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.source_runner import RunPersistSummary
from app.ingestion.statuses import (
    COMPLETED,
    COMPLETED_WITH_ERRORS,
    COMPLETED_WITH_WARNINGS,
    QUARANTINED,
)
from app.ingestion.automation_statuses import MACHINE_READY_ENABLED
from app.models.entities import SourceRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    source_key: str = "test_src",
    is_active: bool = True,
    source_class: str = "machine_ingest",
    parser: str | None = None,
) -> SourceRegistry:
    if parser is None:
        from app.ingestion.source_adapters import ADAPTER_REGISTRY

        parser = next(iter(ADAPTER_REGISTRY.keys()))

    src = SourceRegistry(
        source_key=source_key,
        source_name=f"Source {source_key}",
    )
    src.source_key = source_key
    src.is_active = is_active
    src.source_class = source_class
    src.lifecycle_state = "runnable"
    src.parser = parser
    src.parser_version = "1.0"
    src.allowed_domains = '["example.com"]'
    src.base_url = "https://example.com/feed"
    src.requires_manual_review = True
    src.public_publish_default = False
    src.automation_status = MACHINE_READY_ENABLED
    return src


def _make_db(source: object) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = source
    return db


def _make_adapter_result(
    *,
    records_fetched: int = 5,
    errors: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        records_fetched=records_fetched,
        records_skipped=0,
        created_records=[],
        review_items=[],
        errors=errors or [],
        success=True,
    )


def _run_with_persist(
    source: object,
    *,
    persist_side_effect=None,
    persist_return: RunPersistSummary | None = None,
    adapter_errors: list | None = None,
):
    """Call run_source_now with adapter and persist_ingestion_result both mocked.

    Args:
        source: the source mock returned by the DB query.
        persist_side_effect: optional callable ``(run_record) -> None`` invoked
            inside the persist mock — use it to set ``run_record.status``.
        persist_return: the ``RunPersistSummary`` the mock returns.
        adapter_errors: passed as ``errors`` on the fake adapter result.
    """
    import app.core.config as _config_mod
    import app.ingestion.source_runner as _runner_mod

    if persist_return is None:
        persist_return = RunPersistSummary()
        persist_return.snapshots_written = 1

    adapter = MagicMock()
    adapter.run.return_value = _make_adapter_result(errors=adapter_errors)
    _fake_factory = types.SimpleNamespace(
        build_adapter=MagicMock(return_value=adapter),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    def _persist_effect(db, src, run, result):
        if persist_side_effect is not None:
            persist_side_effect(run)
        return persist_return

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
        patch.object(_runner_mod, "persist_ingestion_result", side_effect=_persist_effect),
        patch("app.api.routes.admin_sources.update_source_health"),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        from app.api.routes.admin_sources import run_source_now

        return run_source_now(
            source_key=source.source_key,
            request=MagicMock(),
            run_mode="synchronous",
            db=_make_db(source),
            actor=MagicMock(auth_method="jwt"),
        )


# ---------------------------------------------------------------------------
# Status-truth: quarantine guard (core Phase 2 bug regression tests)
# ---------------------------------------------------------------------------


class TestQuarantineStatusGuard:
    def test_quarantined_run_returns_success_false(self) -> None:
        """persist_ingestion_result quarantined the run → success must be False."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(
                persisted_incidents=0,
                persisted_review_items=0,
                snapshots_written=0,
                contract_violations=["no_raw_content"],
            ),
        )

        assert result["success"] is False

    def test_quarantined_run_status_field_is_quarantined(self) -> None:
        """status field in return dict must equal the quarantined constant."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(src, persist_side_effect=_quarantine)
        assert result["status"] == QUARANTINED

    def test_quarantined_run_status_not_overwritten_to_completed(self) -> None:
        """The core bug fix: status must remain QUARANTINED, not be promoted."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(
                contract_violations=["no_parser_version"]
            ),
        )

        assert result["status"] != COMPLETED
        assert result["status"] != COMPLETED_WITH_ERRORS
        assert result["status"] == QUARANTINED

    def test_quarantined_run_pipeline_stage_is_quarantine(self) -> None:
        """pipeline_stage must be set to 'quarantine', not to the COMPLETED constant."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(src, persist_side_effect=_quarantine)
        assert result["pipeline_stage"] == "quarantine"
        assert result["pipeline_stage"] != COMPLETED

    def test_quarantined_run_snapshots_written_is_zero(self) -> None:
        """A quarantined run must not count as a written snapshot."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(snapshots_written=0),
        )
        assert result["snapshots_written"] == 0

    def test_quarantined_run_contract_violations_propagated(self) -> None:
        """contract_violations from the summary must appear verbatim in the response."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(
                contract_violations=["no_raw_content", "no_parser_version"],
                snapshots_written=0,
            ),
        )

        assert "no_raw_content" in result["contract_violations"]
        assert "no_parser_version" in result["contract_violations"]

    def test_quarantined_run_persisted_incidents_is_zero(self) -> None:
        """Nothing should be persisted when the run is quarantined."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(
                persisted_incidents=0,
                persisted_review_items=0,
                snapshots_written=0,
                contract_violations=["no_raw_content"],
            ),
        )
        assert result["persisted_incidents"] == 0
        assert result["persisted_review_items"] == 0


# ---------------------------------------------------------------------------
# Status-truth: completed path
# ---------------------------------------------------------------------------


class TestCompletedStatusTruth:
    def test_clean_run_returns_success_true(self) -> None:
        """No errors and no quarantine → success: True."""
        src = _make_source()
        result = _run_with_persist(src)
        assert result["success"] is True

    def test_clean_run_status_is_completed(self) -> None:
        src = _make_source()
        result = _run_with_persist(src)
        assert result["status"] == COMPLETED

    def test_clean_run_snapshots_written_is_one(self) -> None:
        src = _make_source()
        result = _run_with_persist(src)
        assert result["snapshots_written"] == 1

    def test_clean_run_pipeline_stage_is_completed(self) -> None:
        src = _make_source()
        result = _run_with_persist(src)
        assert result["pipeline_stage"] == COMPLETED

    def test_adapter_errors_yield_completed_with_warnings_and_success_true(self) -> None:
        """completed_with_warnings is still a successful pipeline run."""
        src = _make_source()
        result = _run_with_persist(src, adapter_errors=["parse error on row 3"])
        assert result["status"] == COMPLETED_WITH_WARNINGS
        assert result["success"] is True

    def test_adapter_errors_snapshots_written_is_one(self) -> None:
        """completed_with_warnings still produced a snapshot."""
        src = _make_source()
        result = _run_with_persist(src, adapter_errors=["minor error"])
        assert result["snapshots_written"] == 1

    def test_summary_warnings_propagate_to_response(self) -> None:
        src = _make_source()
        result = _run_with_persist(
            src,
            persist_return=RunPersistSummary(
                snapshots_written=1,
                warnings=["crime_incident_insert_failed"],
            ),
        )
        assert result["warnings"] == ["crime_incident_insert_failed"]

    def test_empty_contract_violations_on_completed(self) -> None:
        src = _make_source()
        result = _run_with_persist(src)
        assert result["contract_violations"] == []


# ---------------------------------------------------------------------------
# Status-truth: persist counts reflected in RunResult
# ---------------------------------------------------------------------------


class TestPersistCountsInRunResult:
    def test_persisted_incidents_from_summary(self) -> None:
        src = _make_source()
        result = _run_with_persist(
            src,
            persist_return=RunPersistSummary(
                persisted_incidents=7,
                persisted_review_items=2,
                skipped_duplicates=3,
            ),
        )
        assert result["persisted_incidents"] == 7
        assert result["persisted_review_items"] == 2
        assert result["duplicates_skipped"] == 3

    def test_zero_counts_reflected_accurately(self) -> None:
        src = _make_source()
        result = _run_with_persist(
            src,
            persist_return=RunPersistSummary(
                persisted_incidents=0,
                persisted_review_items=0,
                skipped_duplicates=0,
            ),
        )
        assert result["persisted_incidents"] == 0
        assert result["persisted_review_items"] == 0
        assert result["duplicates_skipped"] == 0

    def test_quarantined_zero_counts_from_summary(self) -> None:
        """A quarantined run should report zero persisted records."""
        src = _make_source()

        def _quarantine(run):
            run.status = QUARANTINED

        result = _run_with_persist(
            src,
            persist_side_effect=_quarantine,
            persist_return=RunPersistSummary(
                persisted_incidents=0,
                persisted_review_items=0,
                skipped_duplicates=0,
                contract_violations=["no_raw_content"],
            ),
        )
        assert result["persisted_incidents"] == 0
        assert result["persisted_review_items"] == 0
