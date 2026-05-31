"""Tests for the ingestion runtime package (Phase B).

All tests use MagicMock or in-process state — no live database required.
Between tests, module-level singletons (scheduler, health, retry queue,
crawl state, checkpoints) are reset via their ``clear_all()`` helpers.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
from typing import Any

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ─────────────────────────────────────────────────────────────────────────────
# checkpointing
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckPointing:
    def setup_method(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.clear_all()

    def test_save_and_load(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.save("src_a", {"offset": 10}, run_id=1)
        result = checkpointing.load("src_a")
        assert result == {"offset": 10}

    def test_load_missing_returns_none(self):
        from app.ingestion.runtime import checkpointing
        assert checkpointing.load("no_such") is None

    def test_clear_removes_entry(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.save("src_b", {"page": 3}, run_id=2)
        checkpointing.clear("src_b")
        assert checkpointing.load("src_b") is None

    def test_clear_all(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.save("a", 1, run_id=1)
        checkpointing.save("b", 2, run_id=2)
        checkpointing.clear_all()
        assert checkpointing.load("a") is None
        assert checkpointing.load("b") is None

    def test_list_active(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.save("src_c", {"k": "v"}, run_id=99)
        entries = checkpointing.list_active()
        names = [e["source_name"] for e in entries]
        assert "src_c" in names

    def test_cursor_is_isolated(self):
        """Mutating the returned cursor must not affect the stored value."""
        from app.ingestion.runtime import checkpointing
        cursor = {"offset": 0}
        checkpointing.save("src_d", cursor, run_id=1)
        result = checkpointing.load("src_d")
        result["offset"] = 999
        assert checkpointing.load("src_d") == {"offset": 0}

    def test_overwrite_updates_cursor(self):
        from app.ingestion.runtime import checkpointing
        checkpointing.save("src_e", {"x": 1}, run_id=1)
        checkpointing.save("src_e", {"x": 2}, run_id=2)
        assert checkpointing.load("src_e") == {"x": 2}

    def test_thread_safety(self):
        from app.ingestion.runtime import checkpointing
        errors: list[Exception] = []

        def writer(i):
            try:
                checkpointing.save(f"src_{i}", {"n": i}, run_id=i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
# ingestion_log
# ─────────────────────────────────────────────────────────────────────────────


class TestIngestionLog:
    def _make_db(self):
        """Return a minimal mock DB that lets open_run flush and set run.id."""
        db = MagicMock()
        # Simulate flush setting run.id
        def fake_flush(obj=None):
            pass
        db.flush = fake_flush
        db.add = MagicMock()
        return db

    def test_open_run_creates_record(self):
        from app.ingestion.runtime import ingestion_log
        from app.models.entities import IngestionRun
        db = self._make_db()
        run = ingestion_log.open_run(db, "courtlistener")
        assert run.source_name == "courtlistener"
        assert run.status == ingestion_log.STATUS_RUNNING
        db.add.assert_called_once()

    def test_open_run_with_stage(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "test_src", pipeline_stage="fetch")
        assert run.pipeline_stage == "fetch"

    def test_close_run_sets_status_and_time(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.close_run(db, run, status=ingestion_log.STATUS_COMPLETE)
        assert run.status == ingestion_log.STATUS_COMPLETE
        assert run.finished_at is not None

    def test_close_run_default_status(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.close_run(db, run)
        assert run.status == ingestion_log.STATUS_COMPLETE

    def test_increment_counts(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.increment_counts(run, fetched=10, parsed=8, persisted=5, skipped=3, errors=0)
        assert run.fetched_count == 10
        assert run.parsed_count == 8
        assert run.persisted_count == 5
        assert run.skipped_count == 3
        assert run.error_count == 0

    def test_increment_counts_accumulates(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.increment_counts(run, fetched=5)
        ingestion_log.increment_counts(run, fetched=5)
        assert run.fetched_count == 10

    def test_append_error(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.append_error(run, "something failed", payload={"k": "v"})
        assert run.error_count == 1
        assert len(run.errors) == 1
        assert run.errors[0]["msg"] == "something failed"

    def test_append_multiple_errors(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.append_error(run, "err1")
        ingestion_log.append_error(run, "err2")
        assert run.error_count == 2
        assert len(run.errors) == 2

    def test_set_stage(self):
        from app.ingestion.runtime import ingestion_log
        db = self._make_db()
        run = ingestion_log.open_run(db, "src")
        ingestion_log.set_stage(run, "persist")
        assert run.pipeline_stage == "persist"

    def test_status_constants_are_strings(self):
        from app.ingestion.runtime import ingestion_log
        for c in (
            ingestion_log.STATUS_RUNNING,
            ingestion_log.STATUS_COMPLETE,
            ingestion_log.STATUS_FAILED,
            ingestion_log.STATUS_QUARANTINED,
            ingestion_log.STATUS_PARTIAL,
        ):
            assert isinstance(c, str)


# ─────────────────────────────────────────────────────────────────────────────
# source_scheduler
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceScheduler:
    def setup_method(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.clear_all()

    def test_register_and_due_immediately(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_a", interval_seconds=3600)
        due = source_scheduler.due_sources()
        assert "src_a" in due

    def test_not_due_after_mark_ran(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_b", interval_seconds=3600)
        source_scheduler.mark_ran("src_b")
        due = source_scheduler.due_sources()
        assert "src_b" not in due

    def test_due_after_interval_passes(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_c", interval_seconds=10)
        source_scheduler.mark_ran("src_c")
        future = _now() + timedelta(seconds=20)
        due = source_scheduler.due_sources(at=future)
        assert "src_c" in due

    def test_disabled_source_not_due(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_d", interval_seconds=0, enabled=False)
        assert "src_d" not in source_scheduler.due_sources()

    def test_enable_and_disable(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_e", interval_seconds=0)
        source_scheduler.disable("src_e")
        assert "src_e" not in source_scheduler.due_sources()
        source_scheduler.enable("src_e")
        assert "src_e" in source_scheduler.due_sources()

    def test_list_schedule(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_f", interval_seconds=60)
        sched = source_scheduler.list_schedule()
        names = [e["source_name"] for e in sched]
        assert "src_f" in names

    def test_mark_ran_unknown_source_no_error(self):
        from app.ingestion.runtime import source_scheduler
        # Should not raise
        source_scheduler.mark_ran("no_such_source")

    def test_interval_change_updates_next_run(self):
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("src_g", interval_seconds=3600)
        source_scheduler.mark_ran("src_g")
        # Re-register with shorter interval
        source_scheduler.register("src_g", interval_seconds=1)
        future = _now() + timedelta(seconds=2)
        assert "src_g" in source_scheduler.due_sources(at=future)

    def test_thread_safety(self):
        from app.ingestion.runtime import source_scheduler
        errors: list[Exception] = []

        def worker(i):
            try:
                source_scheduler.register(f"thr_{i}", interval_seconds=i * 10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
# source_health
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceHealth:
    def setup_method(self):
        from app.ingestion.runtime import source_health
        source_health.clear_all()

    def test_new_source_is_healthy(self):
        from app.ingestion.runtime import source_health
        assert source_health.is_healthy("new_src")

    def test_success_increments(self):
        from app.ingestion.runtime import source_health
        source_health.record_success("src_a", run_id=1)
        snap = source_health.get_snapshot("src_a")
        assert snap.total_runs == 1
        assert snap.success_rate == 1.0
        assert snap.consecutive_failures == 0

    def test_failure_increments_consecutive(self):
        from app.ingestion.runtime import source_health
        source_health.record_failure("src_b", error="timeout")
        snap = source_health.get_snapshot("src_b")
        assert snap.consecutive_failures == 1
        assert snap.total_runs == 1

    def test_success_resets_consecutive_failures(self):
        from app.ingestion.runtime import source_health
        source_health.record_failure("src_c")
        source_health.record_failure("src_c")
        source_health.record_success("src_c")
        snap = source_health.get_snapshot("src_c")
        assert snap.consecutive_failures == 0

    def test_unhealthy_after_threshold(self):
        from app.ingestion.runtime import source_health
        for _ in range(3):
            source_health.record_failure("src_d")
        snap = source_health.get_snapshot("src_d", max_consecutive_failures=3)
        assert not snap.is_healthy

    def test_success_rate_calculation(self):
        from app.ingestion.runtime import source_health
        source_health.record_success("src_e")
        source_health.record_failure("src_e")
        source_health.record_success("src_e")
        snap = source_health.get_snapshot("src_e")
        assert abs(snap.success_rate - 2 / 3) < 0.001

    def test_get_all_snapshots(self):
        from app.ingestion.runtime import source_health
        source_health.record_success("alpha")
        source_health.record_failure("beta")
        snaps = source_health.get_all_snapshots()
        names = [s.source_name for s in snaps]
        assert "alpha" in names
        assert "beta" in names

    def test_refresh_from_db(self):
        from app.ingestion.runtime import source_health
        from app.models.entities import IngestionRun

        run1 = MagicMock(spec=IngestionRun)
        run1.status = "complete"
        run1.started_at = _now() - timedelta(hours=2)
        run1.finished_at = _now() - timedelta(hours=2)

        run2 = MagicMock(spec=IngestionRun)
        run2.status = "failed"
        run2.started_at = _now() - timedelta(hours=1)
        run2.finished_at = _now() - timedelta(hours=1)

        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            run2,
            run1,
        ]
        source_health.refresh_from_db(db, "src_f")
        snap = source_health.get_snapshot("src_f")
        assert snap.total_runs == 2

    def test_thread_safety(self):
        from app.ingestion.runtime import source_health
        errors: list[Exception] = []

        def worker(i):
            try:
                source_health.record_success(f"src_{i % 5}", run_id=i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
# retry_queue
# ─────────────────────────────────────────────────────────────────────────────


class TestRetryQueue:
    def setup_method(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.clear_all()

    def test_enqueue_and_size(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_a", 1, "timeout", delay_secs=0)
        assert retry_queue.size() == 1

    def test_dequeue_due_returns_items(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_b", 2, "error", delay_secs=0)
        items = retry_queue.dequeue_due()
        assert len(items) == 1
        assert items[0].source_name == "src_b"

    def test_dequeue_removes_item(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_c", 3, "err", delay_secs=0)
        retry_queue.dequeue_due()
        assert retry_queue.size() == 0

    def test_item_not_due_not_dequeued(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_d", 4, "err", delay_secs=9999)
        assert retry_queue.dequeue_due() == []

    def test_enqueue_same_key_increments_attempt(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_e", 5, "err1", delay_secs=0)
        item = retry_queue.enqueue("src_e", 5, "err2", delay_secs=0)
        assert item.attempt == 2
        assert retry_queue.size() == 1

    def test_remove(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_f", 6, "err", delay_secs=9999)
        removed = retry_queue.remove("src_f", 6)
        assert removed is True
        assert retry_queue.size() == 0

    def test_remove_nonexistent_returns_false(self):
        from app.ingestion.runtime import retry_queue
        assert retry_queue.remove("no_src", None) is False

    def test_list_pending(self):
        from app.ingestion.runtime import retry_queue
        retry_queue.enqueue("src_g", 7, "pending", delay_secs=9999)
        pending = retry_queue.list_pending()
        assert len(pending) == 1
        assert pending[0]["source_name"] == "src_g"

    def test_payload_isolation(self):
        from app.ingestion.runtime import retry_queue
        payload = {"key": "original"}
        retry_queue.enqueue("src_h", 8, "err", payload=payload, delay_secs=0)
        payload["key"] = "mutated"
        items = retry_queue.dequeue_due()
        assert items[0].payload["key"] == "original"

    def test_thread_safety(self):
        from app.ingestion.runtime import retry_queue
        errors: list[Exception] = []

        def worker(i):
            try:
                retry_queue.enqueue(f"s_{i}", i, "err", delay_secs=0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
# dedupe
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeParsed:
    source_name: str = "courtlistener"
    docket_id: str | None = "12345"
    docket_number: str | None = "1:21-cv-00001"
    court_code: str | None = "nysd"
    court_name: str | None = None
    caption: str | None = None
    date_filed: object = None
    date_terminated: object = None
    judge_name: str | None = "Judge Smith"
    docket_text: str | None = None
    docket_entry_id: str | None = None
    recap_document_id: str | None = None
    entry_number: int | None = None
    entry_date: object = None
    entry_description: str | None = None
    document_links: list = None  # type: ignore[assignment]
    parties: list = None  # type: ignore[assignment]
    source_url: str | None = None
    source_api_url: str | None = None
    source_public_url: str | None = None
    source_quality: str = "court_record"
    raw: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.document_links is None:
            self.document_links = []
        if self.parties is None:
            self.parties = []
        if self.raw is None:
            self.raw = {}


class TestDedupe:
    def test_compute_record_hash_is_deterministic(self):
        from app.ingestion.runtime.dedupe import compute_record_hash
        p = _FakeParsed()
        h1 = compute_record_hash(p)
        h2 = compute_record_hash(p)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_dockets_produce_different_hashes(self):
        from app.ingestion.runtime.dedupe import compute_record_hash
        p1 = _FakeParsed(docket_id="AAA")
        p2 = _FakeParsed(docket_id="BBB")
        assert compute_record_hash(p1) != compute_record_hash(p2)

    def test_check_parsed_record_no_duplicate(self):
        from app.ingestion.runtime.dedupe import check_parsed_record, DedupeResult
        db = MagicMock()
        db.execute.return_value.scalar.return_value = False
        result = check_parsed_record(db, _FakeParsed())
        assert not result.is_duplicate

    def test_check_parsed_record_content_hash_match(self):
        from app.ingestion.runtime.dedupe import check_parsed_record
        db = MagicMock()
        # First call (snapshot check) returns True
        db.execute.return_value.scalar.return_value = True
        result = check_parsed_record(db, _FakeParsed())
        assert result.is_duplicate
        assert result.match_reason == "content_hash"

    def test_is_duplicate_snapshot_false(self):
        from app.ingestion.runtime.dedupe import is_duplicate_snapshot
        db = MagicMock()
        db.execute.return_value.scalar.return_value = False
        assert not is_duplicate_snapshot(db, "abc123", "courtlistener")

    def test_is_duplicate_snapshot_true(self):
        from app.ingestion.runtime.dedupe import is_duplicate_snapshot
        db = MagicMock()
        db.execute.return_value.scalar.return_value = True
        assert is_duplicate_snapshot(db, "abc123", "courtlistener")

    def test_is_duplicate_record_graceful_on_missing_model(self):
        from app.ingestion.runtime.dedupe import is_duplicate_record
        db = MagicMock()
        db.execute.side_effect = Exception("table does not exist")
        # Should not raise; falls back to False
        assert not is_duplicate_record(db, "ext_id", "src")


# ─────────────────────────────────────────────────────────────────────────────
# crawl_state
# ─────────────────────────────────────────────────────────────────────────────


class TestCrawlState:
    def setup_method(self):
        from app.ingestion.runtime import crawl_state
        crawl_state.clear_all()

    def test_start_creates_state(self):
        from app.ingestion.runtime import crawl_state
        state = crawl_state.start("src_a")
        assert state.source_name == "src_a"
        assert state.total_fetched == 0
        assert state.page == 0

    def test_start_with_cursor(self):
        from app.ingestion.runtime import crawl_state
        state = crawl_state.start("src_b", initial_cursor={"offset": 5})
        assert state.cursor == {"offset": 5}

    def test_advance_increments(self):
        from app.ingestion.runtime import crawl_state
        crawl_state.start("src_c")
        state = crawl_state.advance("src_c", {"offset": 50}, 50)
        assert state.total_fetched == 50
        assert state.page == 1

    def test_advance_accumulates(self):
        from app.ingestion.runtime import crawl_state
        crawl_state.start("src_d")
        crawl_state.advance("src_d", {"offset": 50}, 50)
        state = crawl_state.advance("src_d", {"offset": 100}, 50)
        assert state.total_fetched == 100
        assert state.page == 2

    def test_advance_unknown_source_raises(self):
        from app.ingestion.runtime import crawl_state
        with pytest.raises(KeyError):
            crawl_state.advance("no_such", {}, 0)

    def test_get_returns_none_for_missing(self):
        from app.ingestion.runtime import crawl_state
        assert crawl_state.get("missing") is None

    def test_finish_removes_state(self):
        from app.ingestion.runtime import crawl_state
        crawl_state.start("src_e")
        crawl_state.finish("src_e")
        assert crawl_state.get("src_e") is None

    def test_cursor_isolation(self):
        from app.ingestion.runtime import crawl_state
        cursor = {"offset": 0}
        state = crawl_state.start("src_f", initial_cursor=cursor)
        returned = crawl_state.get("src_f")
        returned.cursor["offset"] = 999
        # Internal state must not be mutated
        fresh = crawl_state.get("src_f")
        assert fresh.cursor["offset"] == 0

    def test_list_active(self):
        from app.ingestion.runtime import crawl_state
        crawl_state.start("src_g")
        crawl_state.start("src_h")
        active = crawl_state.list_active()
        names = [e["source_name"] for e in active]
        assert "src_g" in names
        assert "src_h" in names

    def test_thread_safety(self):
        from app.ingestion.runtime import crawl_state
        errors: list[Exception] = []

        def worker(i):
            try:
                crawl_state.start(f"src_{i}")
                crawl_state.advance(f"src_{i}", {"n": i}, 1)
                crawl_state.finish(f"src_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
# replay_engine
# ─────────────────────────────────────────────────────────────────────────────


class TestReplayEngine:
    def setup_method(self):
        from app.ingestion.runtime import checkpointing, ingestion_log
        checkpointing.clear_all()

    def test_replay_with_no_checkpoint(self):
        """replay() with no saved checkpoint should still call ingest_fn(cursor=None)."""
        from app.ingestion.runtime import replay_engine
        db = MagicMock()
        db.flush = MagicMock()
        db.add = MagicMock()

        called_with: list = []

        def ingest_fn(db_, sn, cursor):
            called_with.append(cursor)
            return 5

        result = replay_engine.replay(db, "src_a", ingest_fn)
        assert result.success
        assert result.records_processed == 5
        assert called_with == [None]

    def test_replay_with_checkpoint_passes_cursor(self):
        from app.ingestion.runtime import replay_engine, checkpointing
        checkpointing.save("src_b", {"offset": 100}, run_id=1)
        db = MagicMock()
        db.flush = MagicMock()
        db.add = MagicMock()

        captured: list = []

        def ingest_fn(db_, sn, cursor):
            captured.append(cursor)
            return 3

        result = replay_engine.replay(db, "src_b", ingest_fn, original_run_id=1)
        assert captured[0] == {"offset": 100}
        assert result.success
        # Checkpoint cleared on success
        assert checkpointing.load("src_b") is None

    def test_replay_on_error_marks_failure(self):
        from app.ingestion.runtime import replay_engine

        def bad_ingest(db_, sn, cursor):
            raise RuntimeError("network error")

        db = MagicMock()
        db.flush = MagicMock()
        db.add = MagicMock()
        result = replay_engine.replay(db, "src_c", bad_ingest)
        assert not result.success
        assert "network error" in result.error

    def test_list_replayable(self):
        from app.ingestion.runtime import replay_engine, checkpointing
        checkpointing.save("replayable_src", {"x": 1}, run_id=10)
        db = MagicMock()
        entries = replay_engine.list_replayable(db)
        names = [e["source_name"] for e in entries]
        assert "replayable_src" in names


# ─────────────────────────────────────────────────────────────────────────────
# ingestion_worker
# ─────────────────────────────────────────────────────────────────────────────


class TestIngestionWorker:
    def setup_method(self):
        from app.ingestion.runtime import (
            checkpointing,
            crawl_state,
            source_health,
            source_scheduler,
        )
        checkpointing.clear_all()
        crawl_state.clear_all()
        source_health.clear_all()
        source_scheduler.clear_all()

    def _make_adapter(self, raw_payloads=None, parsed_records=None):
        from app.ingestion.adapters import RawRecord, ParsedRecord, SourceAdapter

        if raw_payloads is None:
            raw_payloads = [{"id": "1"}]
        if parsed_records is None:
            from datetime import date
            parsed_records = [
                ParsedRecord(
                    source_name="test_src",
                    docket_id="D1",
                    docket_number="1:21-cv-00001",
                    court_code="nysd",
                    court_name=None,
                    caption=None,
                    date_filed=None,
                    date_terminated=None,
                    judge_name="Smith",
                    docket_text=None,
                    docket_entry_id=None,
                    recap_document_id=None,
                    entry_number=None,
                    entry_date=None,
                    entry_description=None,
                    document_links=[],
                    parties=[],
                    source_url=None,
                    source_api_url=None,
                    source_public_url=None,
                    source_quality="court_record",
                    raw={},
                )
            ]

        class _Adapter(SourceAdapter):
            def fetch(self, since):
                return [RawRecord(source_name="test_src", payload=p) for p in raw_payloads]

            def parse(self, raw):
                return parsed_records[0]

            def parse_many(self, raw):
                return parsed_records

        return _Adapter()

    def _make_db(self):
        db = MagicMock()
        db.flush = MagicMock()
        db.add = MagicMock()
        return db

    def test_run_returns_ingestion_run(self):
        from app.ingestion.runtime.ingestion_worker import IngestionWorker
        from app.ingestion.runtime.dedupe import DedupeResult

        adapter = self._make_adapter()
        db = self._make_db()

        with patch("app.ingestion.runtime.ingestion_worker.persist_parsed_record") as mock_persist, \
             patch("app.ingestion.runtime.ingestion_worker.dedupe.check_parsed_record") as mock_dedupe:
            from app.ingestion.persistence import PersistResult
            mock_dedupe.return_value = DedupeResult(is_duplicate=False)
            mock_persist.return_value = PersistResult(persisted=True, skipped=False)

            worker = IngestionWorker(db, adapter)
            run = worker.run("test_src")

        assert run is not None
        assert run.source_name == "test_src"

    def test_run_records_health_success(self):
        from app.ingestion.runtime.ingestion_worker import IngestionWorker
        from app.ingestion.runtime import source_health
        from app.ingestion.runtime.dedupe import DedupeResult

        adapter = self._make_adapter()
        db = self._make_db()

        with patch("app.ingestion.runtime.ingestion_worker.persist_parsed_record") as mock_persist, \
             patch("app.ingestion.runtime.ingestion_worker.dedupe.check_parsed_record") as mock_dedupe:
            from app.ingestion.persistence import PersistResult
            mock_dedupe.return_value = DedupeResult(is_duplicate=False)
            mock_persist.return_value = PersistResult(persisted=True, skipped=False)

            worker = IngestionWorker(db, adapter)
            worker.run("test_src")

        snap = source_health.get_snapshot("test_src")
        assert snap.total_runs == 1

    def test_run_skips_duplicates(self):
        from app.ingestion.runtime.ingestion_worker import IngestionWorker
        from app.ingestion.runtime.dedupe import DedupeResult

        adapter = self._make_adapter()
        db = self._make_db()

        with patch("app.ingestion.runtime.ingestion_worker.persist_parsed_record") as mock_persist, \
             patch("app.ingestion.runtime.ingestion_worker.dedupe.check_parsed_record") as mock_dedupe:
            mock_dedupe.return_value = DedupeResult(is_duplicate=True, match_reason="content_hash")

            worker = IngestionWorker(db, adapter)
            run = worker.run("test_src")

        mock_persist.assert_not_called()
        assert run.skipped_count >= 1

    def test_fatal_exception_marks_failed(self):
        from app.ingestion.runtime.ingestion_worker import IngestionWorker

        class _BrokenAdapter:
            def fetch(self, since):
                raise RuntimeError("fetch boom")
            def parse(self, raw): ...
            def parse_many(self, raw): ...

        db = self._make_db()
        worker = IngestionWorker(db, _BrokenAdapter())
        run = worker.run("broken_src")
        from app.ingestion.runtime import ingestion_log
        assert run.status == ingestion_log.STATUS_FAILED


# ─────────────────────────────────────────────────────────────────────────────
# ingestion_runtime (integration)
# ─────────────────────────────────────────────────────────────────────────────


class TestIngestionRuntime:
    def setup_method(self):
        from app.ingestion.runtime import (
            checkpointing,
            crawl_state,
            source_health,
            source_scheduler,
            retry_queue,
        )
        checkpointing.clear_all()
        crawl_state.clear_all()
        source_health.clear_all()
        source_scheduler.clear_all()
        retry_queue.clear_all()

    def test_instantiation(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        db = MagicMock()
        runtime = IngestionRuntime(db)
        assert runtime is not None

    def test_get_worker_returns_worker(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        from app.ingestion.runtime.ingestion_worker import IngestionWorker
        db = MagicMock()
        runtime = IngestionRuntime(db)
        adapter = MagicMock()
        worker = runtime.get_worker(adapter)
        assert isinstance(worker, IngestionWorker)

    def test_can_replay_false_when_no_checkpoint(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        db = MagicMock()
        runtime = IngestionRuntime(db)
        assert not runtime.can_replay("no_src")

    def test_can_replay_true_with_checkpoint(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        from app.ingestion.runtime import checkpointing
        checkpointing.save("src_with_ckpt", {"x": 1}, run_id=5)
        db = MagicMock()
        runtime = IngestionRuntime(db)
        assert runtime.can_replay("src_with_ckpt")

    def test_due_sources_delegates_to_scheduler(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        from app.ingestion.runtime import source_scheduler
        source_scheduler.register("due_src", interval_seconds=0)
        db = MagicMock()
        runtime = IngestionRuntime(db)
        assert "due_src" in runtime.due_sources()

    def test_is_healthy_true_for_new_source(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        db = MagicMock()
        runtime = IngestionRuntime(db)
        assert runtime.is_healthy("brand_new_src")

    def test_list_replayable(self):
        from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
        from app.ingestion.runtime import checkpointing
        checkpointing.save("replayable", {"ts": "2024-01-01"}, run_id=7)
        db = MagicMock()
        runtime = IngestionRuntime(db)
        entries = runtime.list_replayable()
        assert any(e["source_name"] == "replayable" for e in entries)
