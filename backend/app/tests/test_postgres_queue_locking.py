"""Tests for Postgres queue row-level locking behavior."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.workers.postgres_queue import PostgresIngestionQueue
from app.models.entities import IngestionQueueJob
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def _clean_queue_tables():
    db = SessionLocal()
    try:
        db.query(IngestionQueueJob).delete()
        db.commit()
        yield
    finally:
        db.query(IngestionQueueJob).delete()
        db.commit()
        db.close()


def test_lease_next_job_acquires_lock():
    """Test that lease_next_job acquires a lock on a pending job."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"
    source_key = "test_source"

    # Enqueue a job
    job_id = queue.enqueue_job(source_key)

    # Lease the job
    leased_job_id = queue.lease_next_job(worker_id, lease_seconds=300)

    assert leased_job_id == job_id

    # Verify lock was acquired
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job is not None
        assert job.locked_by == worker_id
        assert job.locked_at is not None
        assert job.lease_expires_at is not None
        assert job.state == "running"
    finally:
        db.close()


def test_lease_next_job_skips_locked_jobs():
    """Test that lease_next_job skips jobs already locked by other workers."""
    queue = PostgresIngestionQueue()
    worker1 = f"worker-{uuid.uuid4()}"
    worker2 = f"worker-{uuid.uuid4()}"

    # Enqueue two jobs
    job_id1 = queue.enqueue_job("source1")
    job_id2 = queue.enqueue_job("source2")

    # Worker 1 leases first job
    leased1 = queue.lease_next_job(worker1, lease_seconds=300)
    assert leased1 == job_id1

    # Worker 2 should get the second job, not the first
    leased2 = queue.lease_next_job(worker2, lease_seconds=300)
    assert leased2 == job_id2
    assert leased2 != job_id1


def test_lease_next_job_recovers_stale_locks():
    """Test that lease_next_job recovers jobs with expired leases."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"

    # Enqueue a job
    job_id = queue.enqueue_job("test_source")

    # Manually create a stale lock
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.locked_by = "old-worker"
        job.locked_at = datetime.now(timezone.utc)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)  # Expired
        job.state = "running"
        db.commit()
    finally:
        db.close()

    # Lease should recover the stale lock and assign to new worker
    leased_job_id = queue.lease_next_job(worker_id, lease_seconds=300)
    assert leased_job_id == job_id

    # Verify lock was reassigned
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.locked_by == worker_id
        assert job.lease_expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
    finally:
        db.close()


def test_complete_job_releases_lock():
    """Test that complete_job releases the lock on a job."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"

    # Enqueue and lease a job
    job_id = queue.enqueue_job("test_source")
    queue.lease_next_job(worker_id, lease_seconds=300)

    # Complete the job
    result = {"ok": True, "run_id": 123, "records_fetched": 10}
    queue.complete_job(job_id, worker_id, result)

    # Verify lock was released
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.lease_expires_at is None
        assert job.state == "completed"
    finally:
        db.close()


def test_fail_job_releases_lock_on_retry():
    """Test that fail_job releases lock when scheduling retry."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"

    # Enqueue and lease a job
    job_id = queue.enqueue_job("test_source")
    queue.lease_next_job(worker_id, lease_seconds=300)

    # Fail the job (first failure, should retry)
    queue.fail_job(job_id, worker_id, "Temporary error")

    # Verify lock was released and job is pending for retry
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.lease_expires_at is None
        assert job.state == "pending"
        assert job.retry_count == 1
        assert job.retry_after is not None
    finally:
        db.close()


def test_heartbeat_updates_timestamp():
    """Test that heartbeat_job updates the heartbeat timestamp."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"

    # Enqueue and lease a job
    job_id = queue.enqueue_job("test_source")
    queue.lease_next_job(worker_id, lease_seconds=300)

    # Send heartbeat
    success = queue.heartbeat_job(job_id, worker_id)
    assert success is True

    # Verify heartbeat was updated
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.last_heartbeat_at is not None
        assert job.last_heartbeat_at > datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    finally:
        db.close()


def test_heartbeat_fails_for_wrong_worker():
    """Test that heartbeat_job fails for wrong worker."""
    queue = PostgresIngestionQueue()
    worker1 = f"worker-{uuid.uuid4()}"
    worker2 = f"worker-{uuid.uuid4()}"

    # Enqueue and lease a job with worker1
    job_id = queue.enqueue_job("test_source")
    queue.lease_next_job(worker1, lease_seconds=300)

    # Try to heartbeat with worker2
    success = queue.heartbeat_job(job_id, worker2)
    assert success is False
