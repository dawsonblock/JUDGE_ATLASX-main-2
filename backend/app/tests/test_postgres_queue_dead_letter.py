"""Tests for Postgres queue dead-letter queue behavior."""
import uuid
import pytest

from app.workers.postgres_queue import PostgresIngestionQueue
from app.models.entities import IngestionQueueJob, DeadLetterQueueJob
from app.db.session import SessionLocal


def _clear_tables(db):
    db.query(DeadLetterQueueJob).delete()
    db.query(IngestionQueueJob).delete()


@pytest.fixture(autouse=True)
def _clean_queue_tables():
    db = SessionLocal()
    try:
        _clear_tables(db)
        db.commit()
        yield
    finally:
        _clear_tables(db)
        db.commit()
        db.close()


def test_fail_job_moves_to_dlq_after_max_retries():
    """Test that fail_job moves job to DLQ after max retries."""
    queue = PostgresIngestionQueue()
    queue._retry_delay_seconds = 0
    worker_id = f"worker-{uuid.uuid4()}"
    source_key = "test_source"

    # Enqueue and lease a job
    job_id = queue.enqueue_job(source_key)
    queue.lease_next_job(worker_id, lease_seconds=300)

    # Fail the job 3 times (max_retries = 3)
    for i in range(3):
        queue.fail_job(job_id, worker_id, f"Error attempt {i + 1}")
        # Re-lease for next attempt
        if i < 2:
            queue.lease_next_job(worker_id, lease_seconds=300)

    # Verify job is in DLQ
    db = SessionLocal()
    try:
        dlq_job = (
            db.query(DeadLetterQueueJob)
            .filter(DeadLetterQueueJob.original_job_id == job_id)
            .first()
        )
        assert dlq_job is not None
        assert dlq_job.source_id == source_key
        assert dlq_job.job_type == "ingestion"
        assert dlq_job.attempt_count == 3
        assert dlq_job.final_error is not None
        assert dlq_job.dead_lettered_at is not None

        # Verify original job has dead_lettered_at set
        original_job = (
            db.query(IngestionQueueJob)
            .filter(IngestionQueueJob.job_id == job_id)
            .first()
        )
        assert original_job.dead_lettered_at is not None
        assert original_job.state == "failed"
    finally:
        db.close()


def test_move_to_dead_letter_creates_dlq_record():
    """Test that move_to_dead_letter creates a DLQ record."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"

    # Enqueue a job
    job_id = queue.enqueue_job(source_key)

    # Manually mark as failed
    db = SessionLocal()
    try:
        job = db.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.state = "failed"
        job.error = "Test error"
        job.retry_count = 3
        db.commit()
    finally:
        db.close()

    # Move to DLQ
    success = queue.move_to_dead_letter(job_id)
    assert success is True

    # Verify DLQ record was created
    db = SessionLocal()
    try:
        dlq_job = (
            db.query(DeadLetterQueueJob)
            .filter(DeadLetterQueueJob.original_job_id == job_id)
            .first()
        )
        assert dlq_job is not None
        assert dlq_job.source_id == source_key
        assert dlq_job.job_type == "ingestion"
        assert dlq_job.payload_json is not None
        assert dlq_job.final_error == "Test error"
        assert dlq_job.attempt_count == 3
    finally:
        db.close()


def test_dlq_record_preserves_original_job_data():
    """Test that DLQ record preserves original job data."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"

    # Enqueue a job
    job_id = queue.enqueue_job(source_key)

    # Move to DLQ
    queue.move_to_dead_letter(job_id)

    # Verify original job data is preserved
    db = SessionLocal()
    try:
        dlq_job = (
            db.query(DeadLetterQueueJob)
            .filter(DeadLetterQueueJob.original_job_id == job_id)
            .first()
        )
        assert dlq_job.payload_json is not None
        assert dlq_job.payload_json["job_id"] == job_id
        assert dlq_job.payload_json["source_key"] == source_key
    finally:
        db.close()


def test_move_to_dead_letter_fails_for_nonexistent_job():
    """Test that move_to_dead_letter fails for nonexistent job."""
    queue = PostgresIngestionQueue()

    # Try to move nonexistent job to DLQ
    success = queue.move_to_dead_letter("nonexistent-job-id")
    assert success is False


def test_dlq_job_has_required_fields():
    """Test that DLQ job has all required fields."""
    queue = PostgresIngestionQueue()
    source_key = "test_source"

    # Enqueue a job
    job_id = queue.enqueue_job(source_key)

    # Move to DLQ
    queue.move_to_dead_letter(job_id)

    # Verify all required fields are present
    db = SessionLocal()
    try:
        dlq_job = (
            db.query(DeadLetterQueueJob)
            .filter(DeadLetterQueueJob.original_job_id == job_id)
            .first()
        )
        assert dlq_job.id is not None
        assert dlq_job.original_job_id == job_id
        assert dlq_job.source_id == source_key
        assert dlq_job.job_type == "ingestion"
        assert dlq_job.dead_lettered_at is not None
        assert dlq_job.created_at is not None
    finally:
        db.close()
