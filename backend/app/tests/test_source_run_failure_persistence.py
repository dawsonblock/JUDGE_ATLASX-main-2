"""Regression tests for durable failed-source-run persistence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.admin_sources import run_source_now
from app.tests.test_source_run_policy import _make_db, _make_source


def test_failed_run_is_persisted_after_adapter_exception() -> None:
    import app.core.config as _config_mod
    import app.ingestion.source_runner as _runner_mod

    src = _make_source(source_class="machine_ingest")
    src.automation_status = "machine_ready_enabled"

    db = _make_db(src)
    adapter = MagicMock()
    adapter.run.side_effect = RuntimeError("adapter exploded")

    fake_factory = SimpleNamespace(
        build_adapter=MagicMock(return_value=adapter),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(__import__("sys").modules, {"app.ingestion.source_adapter_factory": fake_factory}),
        patch.object(_runner_mod, "persist_ingestion_result"),
        patch("app.api.routes.admin_sources.update_source_health") as mock_health,
        patch("app.api.routes.admin_sources.log_mutation") as mock_log_mutation,
    ):
        with pytest.raises(HTTPException) as exc_info:
            run_source_now(
                source_key=src.source_key,
                request=MagicMock(),
                run_mode="synchronous",
                db=db,
                actor=MagicMock(auth_method="jwt"),
            )

    assert exc_info.value.status_code == 500
    assert "Source run failed" in str(exc_info.value.detail)

    # Durable failure persistence path: initial commit for running row, then
    # rollback + merge + commit to store failed status and error payload.
    assert db.commit.call_count == 2
    db.rollback.assert_called_once()
    db.merge.assert_called_once()

    mock_health.assert_called_once()
    mock_log_mutation.assert_not_called()
