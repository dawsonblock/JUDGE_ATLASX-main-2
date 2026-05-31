"""Tests for Postgres queue stale lock recovery behavior."""
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


def test_recover_stale_jobs_resets_expired_leases():
    """Test that recover_stale_jobs resets jobs with expired leases."""
    queue = PostgresIngestionQueue()
    worker1 = f"worker-{uuid.uuid4()}"
    worker2 = f"worker-{uuid.uuid4()}"

    # Enqueue a job
    job_id = queue.enqueue_job("test_source")

    # Manually create an expired lease
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.locked_by = worker1
        job.locked_at = datetime.now(timezone.utc)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)  # Expired
        job.state = "running"
        db.commit()
    finally:
        db.close()

    # Run stale job recovery
    queue.recover_stale_jobs()

    # Verify job was recovered to pending state
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.state == "pending"
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.lease_expires_at is None
        assert job.retry_count == 1
    finally:
        db.close()


def test_recover_stale_jobs_does_not_affect_active_leases():
    """Test that recover_stale_jobs does not affect jobs with active leases."""
    queue = PostgresIngestionQueue()
    worker_id = f"worker-{uuid.uuid4()}"

    # Enqueue a job
    job_id = queue.enqueue_job("test_source")

    # Manually create an active lease
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.locked_by = worker_id
        job.locked_at = datetime.now(timezone.utc)
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)  # Active
        job.state = "running"
        db.commit()
    finally:
        db.close()

    # Run stale job recovery
    queue.recover_stale_jobs()

    # Verify job was NOT recovered (still locked)
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.state == "running"
        assert job.locked_by == worker_id
        assert job.lease_expires_at is not None
        assert job.lease_expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
    finally:
        db.close()


def test_lease_next_job_recovers_stale_locks_automatically():
    """Test that lease_next_job recovers stale locks before leasing."""
    queue = PostgresIngestionQueue()
    worker1 = f"worker-{uuid.uuid4()}"
    worker2 = f"worker-{uuid.uuid4()}"

    # Enqueue a job
    job_id = queue.enqueue_job("test_source")

    # Manually create an expired lease
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.locked_by = worker1
        job.locked_at = datetime.now(timezone.utc)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)  # Expired
        job.state = "running"
        db.commit()
    finally:
        db.close()

    # Try to lease with worker2 - should recover stale lock and lease to worker2
    leased_job_id = queue.lease_next_job(worker2, lease_seconds=300)
    assert leased_job_id == job_id

    # Verify job was leased to worker2
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.locked_by == worker2
        assert job.lease_expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
        assert job.retry_count == 1  # Incremented by recovery
    finally:
        db.close()


def test_recover_stale_jobs_increments_retry_count():
    """Test that recover_stale_jobs increments retry count."""
    queue = PostgresIngestionQueue()

    # Enqueue a job
    job_id = queue.enqueue_job("test_source")

    # Manually create an expired lease
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.locked_by = "old-worker"
        job.locked_at = datetime.now(timezone.utc)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        job.state = "running"
        job.retry_count = 2
        db.commit()
    finally:
        db.close()

    # Run stale job recovery
    queue.recover_stale_jobs()

    # Verify retry count was incremented
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.retry_count == 3
    finally:
        db.close()


def test_recover_stale_jobs_handles_multiple_stale_jobs():
    """Test that recover_stale_jobs handles multiple stale jobs."""
    queue = PostgresIngestionQueue()

    # Enqueue multiple jobs
    job_ids = [queue.enqueue_job(f"source{i}") for i in range(3)]

    # Manually create expired leases for all jobs
    db = SessionLocal()
    try:
        for job_id in job_ids:
            job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
            job.locked_by = "old-worker"
            job.locked_at = datetime.now(timezone.utc)
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)
            job.state = "running"
        db.commit()
    finally:
        db.close()

    # Run stale job recovery
    queue.recover_stale_jobs()

    # Verify all jobs were recovered
    db = SessionLocal()
    try:
        for job_id in job_ids:
            job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
            assert job.state == "pending"
            assert job.locked_by is None
            assert job.lease_expires_at is None
    finally:
        db.close()


def test_recover_stale_jobs_handles_no_stale_jobs():
    """Test that recover_stale_jobs handles case with no stale jobs."""
    queue = PostgresIngestionQueue()

    # Enqueue a job with active lease
    job_id = queue.enqueue_job("test_source")
    worker_id = f"worker-{uuid.uuid4()}"
    queue.lease_next_job(worker_id, lease_seconds=300)

    # Run stale job recovery - should not raise error
    queue.recover_stale_jobs()

    # Verify job was not affected
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job.state == "running"
        assert job.locked_by == worker_id
    finally:
        db.close()
