"""Tests for Postgres queue idempotency key behavior."""
import uuid
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


def test_enqueue_job_with_idempotency_key():
    """Test that enqueue_job with idempotency key prevents duplicates."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"
    idempotency_key = "unique-key-123"

    # Enqueue job with idempotency key
    job_id1 = queue.enqueue_job(source_key, idempotency_key=idempotency_key)

    # Try to enqueue same job again with same idempotency key
    job_id2 = queue.enqueue_job(source_key, idempotency_key=idempotency_key)

    # Should return the same job ID
    assert job_id1 == job_id2

    # Verify only one job exists in database
    db = SessionLocal()
    try:
        jobs = (
            db.query(IngestionQueueJob)
            .filter(
                IngestionQueueJob.source_key == source_key,
                IngestionQueueJob.idempotency_key == idempotency_key,
            )
            .all()
        )
        assert len(jobs) == 1
        assert jobs[0].job_id == job_id1
    finally:
        db.close()


def test_enqueue_job_without_idempotency_key():
    """Test that enqueue_job without idempotency key creates new job each time."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"

    # Enqueue job without idempotency key
    job_id1 = queue.enqueue_job(source_key)

    # Enqueue another job without idempotency key
    job_id2 = queue.enqueue_job(source_key)

    # Should create different job IDs
    assert job_id1 != job_id2

    # Verify two jobs exist in database
    db = SessionLocal()
    try:
        jobs = (
            db.query(IngestionQueueJob)
            .filter(IngestionQueueJob.source_key == source_key)
            .all()
        )
        assert len(jobs) == 2
    finally:
        db.close()


def test_different_idempotency_keys_create_different_jobs():
    """Test that different idempotency keys create different jobs."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"

    # Enqueue jobs with different idempotency keys
    job_id1 = queue.enqueue_job(source_key, idempotency_key="key-1")
    job_id2 = queue.enqueue_job(source_key, idempotency_key="key-2")

    # Should create different job IDs
    assert job_id1 != job_id2

    # Verify two jobs exist in database
    db = SessionLocal()
    try:
        jobs = (
            db.query(IngestionQueueJob)
            .filter(IngestionQueueJob.source_key == source_key)
            .all()
        )
        assert len(jobs) == 2
    finally:
        db.close()


def test_idempotency_key_with_different_source_keys():
    """Test that same idempotency key with different source keys creates different jobs."""
    queue = PostgresIngestionQueue()
    idempotency_key = "shared-key-123"

    # Enqueue jobs for different sources with same idempotency key
    job_id1 = queue.enqueue_job("source1", idempotency_key=idempotency_key)
    job_id2 = queue.enqueue_job("source2", idempotency_key=idempotency_key)

    # Should create different job IDs (unique constraint is on source_key + idempotency_key)
    assert job_id1 != job_id2

    # Verify two jobs exist in database
    db = SessionLocal()
    try:
        jobs = db.query(IngestionQueueJob).filter(
            IngestionQueueJob.idempotency_key == idempotency_key
        ).all()
        assert len(jobs) == 2
    finally:
        db.close()
