from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.runner import run_courtlistener_ingestion


@contextmanager
def _advisory_lock_acquired(*_args, **_kwargs):
    yield True


def _base_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="development", courtlistener_max_dockets_per_run=10)


def test_run_courtlistener_ingestion_commit_false_success_does_not_commit() -> None:
    db = MagicMock()
    adapter = MagicMock()
    adapter.fetch.return_value = []
    adapter.errors = []

    with (
        patch("app.ingestion.runner.get_settings", return_value=_base_settings()),
        patch(
            "app.ingestion.runner.require_source_registry",
            return_value=SimpleNamespace(id=1),
        ),
        patch(
            "app.ingestion.runner.check_ingestion_allowed", return_value=(True, None)
        ),
        patch(
            "app.ingestion.runner.advisory_lock", side_effect=_advisory_lock_acquired
        ),
        patch("app.ingestion.runner.CourtListenerAdapter", new=lambda: adapter),
        patch("app.ingestion.runner.update_source_health") as update_health,
    ):
        run_courtlistener_ingestion(db, datetime.now(timezone.utc), commit=False)

    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.refresh.assert_not_called()
    update_health.assert_called_once()
    assert update_health.call_args.kwargs["auto_commit"] is False


def test_run_courtlistener_ingestion_commit_false_disabled_source_does_not_commit_or_rollback() -> (
    None
):
    db = MagicMock()

    with (
        patch("app.ingestion.runner.get_settings", return_value=_base_settings()),
        patch(
            "app.ingestion.runner.require_source_registry",
            return_value=SimpleNamespace(id=1),
        ),
        patch(
            "app.ingestion.runner.check_ingestion_allowed",
            return_value=(False, "disabled"),
        ),
    ):
        run_courtlistener_ingestion(db, datetime.now(timezone.utc), commit=False)

    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_run_courtlistener_ingestion_commit_false_adapter_missing_does_not_commit_or_rollback() -> (
    None
):
    db = MagicMock()

    with (
        patch("app.ingestion.runner.get_settings", return_value=_base_settings()),
        patch(
            "app.ingestion.runner.require_source_registry",
            return_value=SimpleNamespace(id=1),
        ),
        patch(
            "app.ingestion.runner.check_ingestion_allowed", return_value=(True, None)
        ),
        patch(
            "app.ingestion.runner.advisory_lock", side_effect=_advisory_lock_acquired
        ),
        patch(
            "app.ingestion.runner.CourtListenerAdapter",
            new=lambda: (_ for _ in ()).throw(RuntimeError("adapter missing")),
        ),
    ):
        with pytest.raises(RuntimeError, match="adapter missing"):
            run_courtlistener_ingestion(db, datetime.now(timezone.utc), commit=False)

    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_run_courtlistener_ingestion_commit_false_adapter_failure_does_not_commit_before_audit() -> (
    None
):
    db = MagicMock()
    adapter = MagicMock()
    adapter.fetch.side_effect = RuntimeError("adapter exploded")
    adapter.errors = []

    with (
        patch("app.ingestion.runner.get_settings", return_value=_base_settings()),
        patch(
            "app.ingestion.runner.require_source_registry",
            return_value=SimpleNamespace(id=1),
        ),
        patch(
            "app.ingestion.runner.check_ingestion_allowed", return_value=(True, None)
        ),
        patch(
            "app.ingestion.runner.advisory_lock", side_effect=_advisory_lock_acquired
        ),
        patch("app.ingestion.runner.CourtListenerAdapter", new=lambda: adapter),
    ):
        run = run_courtlistener_ingestion(db, datetime.now(timezone.utc), commit=False)

    assert run.status == "failed"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_run_courtlistener_ingestion_commit_true_commits_only_at_final_point() -> None:
    db = MagicMock()
    adapter = MagicMock()
    adapter.fetch.return_value = []
    adapter.errors = []

    with (
        patch("app.ingestion.runner.get_settings", return_value=_base_settings()),
        patch(
            "app.ingestion.runner.require_source_registry",
            return_value=SimpleNamespace(id=1),
        ),
        patch(
            "app.ingestion.runner.check_ingestion_allowed", return_value=(True, None)
        ),
        patch(
            "app.ingestion.runner.advisory_lock", side_effect=_advisory_lock_acquired
        ),
        patch("app.ingestion.runner.CourtListenerAdapter", new=lambda: adapter),
        patch("app.ingestion.runner.update_source_health") as update_health,
    ):
        run_courtlistener_ingestion(db, datetime.now(timezone.utc), commit=True)

    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    update_health.assert_called_once()
    assert update_health.call_args.kwargs["auto_commit"] is False
