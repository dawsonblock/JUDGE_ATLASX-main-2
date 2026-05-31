from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.session import SessionLocal
from app.models.entities import IngestionQueueJob
from app.workers.inprocess_queue import InProcessIngestionQueue
from app.workers.postgres_queue import PostgresIngestionQueue
from app.workers.queue_backend import JobState


@pytest.fixture(autouse=True)
def _clean_queue_jobs() -> None:
    db = SessionLocal()
    try:
        db.query(IngestionQueueJob).delete()
        db.commit()
        yield
    finally:
        db.query(IngestionQueueJob).delete()
        db.commit()
        db.close()


def test_inprocess_cancel_marks_failed_and_removes_pending() -> None:
    queue = InProcessIngestionQueue()
    job_id = queue.enqueue("source_a")

    canceled = queue.cancel_job(job_id)

    assert canceled is not None
    assert canceled.state == JobState.CANCELLED
    assert canceled.error == "Canceled by admin"
    assert queue.pending_count() == 0


def test_inprocess_retry_requires_terminal_job() -> None:
    queue = InProcessIngestionQueue()
    job_id = queue.enqueue("source_a")

    with pytest.raises(ValueError):
        queue.retry_job(job_id)


def test_inprocess_retry_creates_new_pending_job_from_failed() -> None:
    queue = InProcessIngestionQueue()
    failed_job_id = queue.enqueue("source_a")
    queue.cancel_job(failed_job_id)

    retried_job_id = queue.retry_job(failed_job_id)

    assert retried_job_id is not None
    retried = queue.get_status(retried_job_id)
    assert retried is not None
    assert retried.source_key == "source_a"
    assert retried.state == JobState.PENDING


def test_postgres_cancel_marks_failed_and_clears_lease_fields() -> None:
    queue = PostgresIngestionQueue()
    worker_id = "worker-test"
    job_id = queue.enqueue_job("source_a")
    queue.lease_next_job(worker_id, lease_seconds=300)

    canceled = queue.cancel_job(job_id)

    assert canceled is not None
    assert canceled.state == JobState.CANCELLED
    assert canceled.error == "Canceled by admin"

    db = SessionLocal()
    try:
        row = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert row is not None
        assert row.state == JobState.CANCELLED.value
        assert row.locked_by is None
        assert row.locked_at is None
        assert row.lease_expires_at is None
    finally:
        db.close()


def test_postgres_retry_requires_terminal_state() -> None:
    queue = PostgresIngestionQueue()
    job_id = queue.enqueue_job("source_a")

    with pytest.raises(ValueError):
        queue.retry_job(job_id)


def test_postgres_retry_creates_new_pending_job() -> None:
    queue = PostgresIngestionQueue()
    old_job_id = queue.enqueue_job("source_b")

    db = SessionLocal()
    try:
        row = db.query(IngestionQueueJob).filter_by(job_id=old_job_id).first()
        assert row is not None
        row.state = JobState.COMPLETED.value
        row.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    new_job_id = queue.retry_job(old_job_id)

    assert new_job_id is not None
    new_status = queue.get_status(new_job_id)
    assert new_status is not None
    assert new_status.state == JobState.PENDING
    assert new_status.source_key == "source_b"
