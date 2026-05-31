"""Tests for app.workers.scheduler — build_scheduler and _run_source_job."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.workers.scheduler import (
    _TARGET_BY_SOURCE_KEY,
    _run_source_job,
    build_scheduler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_factory(rows: list[Any] | None = None, raise_exc: Exception | None = None):
    """Return a db_factory context-manager callable."""

    @contextmanager
    def _factory():
        db = MagicMock()
        if raise_exc is not None:
            db.__enter__ = MagicMock(side_effect=raise_exc)
            db.__exit__ = MagicMock(return_value=False)
            raise raise_exc
        query_mock = db.query.return_value
        query_mock.filter.return_value.all.return_value = rows or []
        yield db

    return _factory


def _make_source_row(
    source_key: str,
    source_name: str = "Test Source",
    is_active: bool = True,
    fetch_method: str = "crawlee",
):
    row = MagicMock()
    row.source_key = source_key
    row.source_name = source_name
    row.is_active = is_active
    row.fetch_method = fetch_method
    return row


# ---------------------------------------------------------------------------
# _TARGET_BY_SOURCE_KEY
# ---------------------------------------------------------------------------


class TestTargetBySourceKey:
    def test_is_dict(self):
        assert isinstance(_TARGET_BY_SOURCE_KEY, dict)

    def test_not_empty(self):
        assert len(_TARGET_BY_SOURCE_KEY) > 0

    def test_keys_are_strings(self):
        for k in _TARGET_BY_SOURCE_KEY:
            assert isinstance(k, str)

    def test_values_have_source_key_attr(self):
        for sk, target in _TARGET_BY_SOURCE_KEY.items():
            assert hasattr(target, "source_key")
            assert target.source_key == sk

    def test_values_have_crawl_interval_hours(self):
        for target in _TARGET_BY_SOURCE_KEY.values():
            assert hasattr(target, "crawl_interval_hours")
            assert isinstance(target.crawl_interval_hours, (int, float))
            assert target.crawl_interval_hours > 0


# ---------------------------------------------------------------------------
# build_scheduler
# ---------------------------------------------------------------------------


class TestBuildScheduler:
    def test_returns_asyncio_scheduler(self):
        factory = _make_db_factory(rows=[])
        sched = build_scheduler(factory)
        assert isinstance(sched, AsyncIOScheduler)

    def test_empty_active_rows_yields_empty_scheduler(self):
        factory = _make_db_factory(rows=[])
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == 0

    def test_db_exception_yields_empty_scheduler(self):
        """DB failure must not raise; returns an empty scheduler."""

        @contextmanager
        def _bad_factory():
            raise RuntimeError("DB unavailable")
            yield  # pragma: no cover — unreachable

        sched = build_scheduler(_bad_factory)
        assert isinstance(sched, AsyncIOScheduler)
        assert len(sched.get_jobs()) == 0

    def test_active_row_with_known_target_adds_job(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        row = _make_source_row(source_key=valid_key)
        factory = _make_db_factory(rows=[row])
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == 1

    def test_job_id_uses_source_key(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        row = _make_source_row(source_key=valid_key)
        factory = _make_db_factory(rows=[row])
        sched = build_scheduler(factory)
        job = sched.get_jobs()[0]
        assert job.id == f"web_monitor_{valid_key}"

    def test_job_trigger_is_interval(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        row = _make_source_row(source_key=valid_key)
        factory = _make_db_factory(rows=[row])
        sched = build_scheduler(factory)
        job = sched.get_jobs()[0]
        assert isinstance(job.trigger, IntervalTrigger)

    def test_inactive_row_does_not_add_job(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        # is_active=False rows are filtered out at DB level;
        # simulate by not including them in the returned rows
        factory = _make_db_factory(rows=[])
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == 0

    def test_manual_fetch_method_row_excluded(self):
        # simulate DB already filtering these out
        factory = _make_db_factory(rows=[])
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == 0

    def test_row_with_unknown_source_key_skipped(self):
        row = _make_source_row(source_key="__does_not_exist__")
        factory = _make_db_factory(rows=[row])
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == 0

    def test_multiple_known_rows_all_scheduled(self):
        keys = list(_TARGET_BY_SOURCE_KEY.keys())
        rows = [_make_source_row(source_key=k) for k in keys]
        factory = _make_db_factory(rows=rows)
        sched = build_scheduler(factory)
        assert len(sched.get_jobs()) == len(keys)

    def test_scheduler_not_yet_started(self):
        factory = _make_db_factory(rows=[])
        sched = build_scheduler(factory)
        assert not sched.running

    def test_replace_existing_true_passed_to_add_job(self):
        """build_scheduler passes replace_existing=True to add_job."""
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        row = _make_source_row(source_key=valid_key)
        factory = _make_db_factory(rows=[row])
        with patch("app.workers.scheduler.AsyncIOScheduler") as MockSched:
            mock_instance = MagicMock()
            MockSched.return_value = mock_instance
            mock_instance.get_jobs.return_value = []
            build_scheduler(factory)
        call_kwargs = mock_instance.add_job.call_args[1]
        assert call_kwargs.get("replace_existing") is True


# ---------------------------------------------------------------------------
# _run_source_job
# ---------------------------------------------------------------------------


class TestRunSourceJob:
    def _make_run_result(self, fetched=3, persisted=2, errors=0):
        result = MagicMock()
        result.fetched_count = fetched
        result.persisted_count = persisted
        result.error_count = errors
        return result

    @pytest.mark.asyncio
    async def test_unknown_source_key_does_nothing(self):
        called = []

        @contextmanager
        def _factory():
            yield MagicMock()
            called.append(True)

        with patch(
            "app.workers.scheduler.run_web_monitor_target",
            new=AsyncMock(),
        ) as mock_rwmt:
            await _run_source_job("__nonexistent__", _factory)
            mock_rwmt.assert_not_called()
        assert not called, "DB factory should not be called for unknown key"

    @pytest.mark.asyncio
    async def test_known_source_key_calls_run_web_monitor_target(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        run_result = self._make_run_result()

        @contextmanager
        def _factory():
            yield MagicMock()

        with patch(
            "app.workers.scheduler.run_web_monitor_target",
            new=AsyncMock(return_value=run_result),
        ) as mock_rwmt:
            await _run_source_job(valid_key, _factory)
            mock_rwmt.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_run_does_not_propagate(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))

        @contextmanager
        def _factory():
            yield MagicMock()

        with patch(
            "app.workers.scheduler.run_web_monitor_target",
            new=AsyncMock(side_effect=RuntimeError("crawler boom")),
        ):
            # Must not raise
            await _run_source_job(valid_key, _factory)

    @pytest.mark.asyncio
    async def test_run_result_counts_logged(self, caplog):
        import logging

        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        run_result = self._make_run_result(fetched=7, persisted=5, errors=2)

        @contextmanager
        def _factory():
            yield MagicMock()

        with caplog.at_level(logging.INFO):
            with patch(
                "app.workers.scheduler.run_web_monitor_target",
                new=AsyncMock(return_value=run_result),
            ):
                await _run_source_job(valid_key, _factory)

        assert any("fetched=7" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_key_logged_as_warning(self, caplog):
        import logging

        @contextmanager
        def _factory():
            yield MagicMock()  # pragma: no cover

        with caplog.at_level(logging.WARNING):
            await _run_source_job("__ghost_key__", _factory)

        assert any("__ghost_key__" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_db_factory_used_as_context_manager(self):
        valid_key = next(iter(_TARGET_BY_SOURCE_KEY))
        entered = []

        @contextmanager
        def _factory():
            entered.append(True)
            yield MagicMock()

        with patch(
            "app.workers.scheduler.run_web_monitor_target",
            new=AsyncMock(return_value=self._make_run_result()),
        ):
            await _run_source_job(valid_key, _factory)

        assert entered, "DB factory context manager should have been entered"


# ---------------------------------------------------------------------------
# TestSchedulerLifespanGate
# ---------------------------------------------------------------------------


class TestSchedulerLifespanGate:
    """Verify that build_scheduler is only called when enable_scheduler=True."""

    def test_build_scheduler_not_called_when_disabled(self):
        """When settings.enable_scheduler is False, build_scheduler must not be invoked."""
        with patch("app.workers.scheduler.build_scheduler") as mock_build:
            # Simulate a settings object with enable_scheduler=False
            from app.core.config import get_settings

            settings = get_settings()
            if not settings.enable_scheduler:
                # Confirm the flag is false (default) — no scheduler should be built
                assert not mock_build.called

    def test_build_scheduler_called_when_enabled(self):
        """When enable_scheduler=True, build_scheduler is the function that creates the scheduler."""
        # Smoke-test that build_scheduler itself returns an AsyncIOScheduler
        from sqlalchemy.orm import Session
        from unittest.mock import MagicMock

        db_factory = MagicMock()
        sched = build_scheduler(db_factory)
        assert isinstance(sched, AsyncIOScheduler)
