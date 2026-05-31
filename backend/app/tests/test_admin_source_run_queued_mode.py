"""Tests for queued mode in admin_sources.run_source_now."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

from app.api.routes.admin_sources import run_source_now
from app.tests.test_source_run_policy import _make_db, _make_source


class _FakeQueue:
    def __init__(self) -> None:
        self.job_id = "queued-job-1"
        self.enqueued: list[str] = []

    def enqueue(self, source_key: str) -> str:
        self.enqueued.append(source_key)
        return self.job_id


def test_run_source_now_queued_mode_returns_job(monkeypatch) -> None:
    import app.core.config as _config_mod

    src = _make_source(source_class="machine_ingest")
    src.automation_status = "machine_ready_enabled"

    db = _make_db(src)
    fake_queue = _FakeQueue()

    fake_factory = types.SimpleNamespace(
        build_adapter=MagicMock(return_value=MagicMock()),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": fake_factory}),
        patch("app.api.routes.admin_sources.get_ingestion_queue", return_value=fake_queue),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        result = run_source_now(
            source_key=src.source_key,
            request=MagicMock(),
            run_mode="queued",
            db=db,
            actor=MagicMock(auth_method="jwt"),
        )

    assert result["run_mode"] == "queued"
    assert result["job_id"] == "queued-job-1"
    assert result["status"] == "queued"
    assert result["run_id"] is None
    assert result["success"] is False
    assert fake_queue.enqueued == [src.source_key]
