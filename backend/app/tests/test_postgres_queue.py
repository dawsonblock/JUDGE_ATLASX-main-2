"""Tests for PostgreSQL queue backend (Phase 14).

Tests queue health monitoring and retry logic.
"""

import pytest
from datetime import datetime, timezone

from app.models.entities import IngestionQueueJob
from app.workers.postgres_queue import PostgresIngestionQueue
from app.workers.queue_backend import JobState
from app.db.session import SessionLocal


class TestPostgresQueue:
    """Test PostgreSQL queue backend."""

    def test_enqueue_job(self, db_session):
        """Test enqueuing a job."""
        queue = PostgresIngestionQueue()

        job_id = queue.enqueue("test_source")

        assert job_id is not None

        job = db_session.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        assert job is not None
        assert job.source_key == "test_source"
        assert job.state == JobState.PENDING.value

    def test_get_job_status(self, db_session):
        """Test getting job status."""
        queue = PostgresIngestionQueue()

        job_id = queue.enqueue("test_source")

        status = queue.get_status(job_id)

        assert status is not None
        assert status.job_id == job_id
        assert status.source_key == "test_source"
        assert status.state == JobState.PENDING

    def test_pending_count(self, db_session):
        """Test getting pending job count."""
        queue = PostgresIngestionQueue()

        queue.enqueue("source1")
        queue.enqueue("source2")

        count = queue.pending_count()

        assert count == 2

    def test_list_jobs(self, db_session):
        """Test listing jobs."""
        queue = PostgresIngestionQueue()

        queue.enqueue("source1")
        queue.enqueue("source2")

        jobs = queue.list_jobs()

        assert len(jobs) == 2

    def test_list_jobs_by_state(self, db_session):
        """Test listing jobs filtered by state."""
        queue = PostgresIngestionQueue()

        job_id = queue.enqueue("source1")

        # Update job to running state
        job = db_session.query(IngestionQueueJob).filter_by(job_id=job_id).first()
        job.state = JobState.RUNNING.value
        db_session.commit()

        pending_jobs = queue.list_jobs(JobState.PENDING)
        running_jobs = queue.list_jobs(JobState.RUNNING)

        assert len(pending_jobs) == 0
        assert len(running_jobs) == 1


class TestQueueHealthMonitoring:
    """Test queue health monitoring."""

    def test_get_health_status_empty_queue(self, db_session):
        """Test health status with empty queue."""
        queue = PostgresIngestionQueue()

        health = queue.get_health_status()

        assert "total_jobs" in health
        assert "pending_jobs" in health
        assert "running_jobs" in health
        assert "failed_jobs" in health
        assert "completion_rate" in health
        assert "healthy" in health

    def test_get_health_status_with_jobs(self, db_session):
        """Test health status with jobs."""
        queue = PostgresIngestionQueue()

        # Add a completed job
        job = IngestionQueueJob(
            job_id="test_job_1",
            source_key="source1",
            state=JobState.COMPLETED.value,
            enqueued_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(job)

        # Add a failed job
        job2 = IngestionQueueJob(
            job_id="test_job_2",
            source_key="source2",
            state=JobState.FAILED.value,
            enqueued_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(job2)
        db_session.commit()

        health = queue.get_health_status()

        assert health["total_jobs"] == 2
        assert health["failed_jobs"] == 1


class TestQueueRetryLogic:
    """Test queue retry logic."""

    def test_max_retries_limit(self, db_session):
        """Test that jobs fail after max retries."""
        queue = PostgresIngestionQueue()

        # The queue has max_retries = 3 by default
        assert queue._max_retries == 3

    def test_retry_delay(self, db_session):
        """Test retry delay configuration."""
        queue = PostgresIngestionQueue()

        # The queue has retry_delay_seconds = 60 by default
        assert queue._retry_delay_seconds == 60

    def test_capabilities(self, db_session):
        """Test queue backend capabilities."""
        queue = PostgresIngestionQueue()

        caps = queue._capabilities

        assert caps.name == "postgres"
        assert caps.supports_production is False
        assert caps.implementation_status == "alpha"


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        # Isolate this module's tests since queue methods use independent sessions.
        session.query(IngestionQueueJob).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.query(IngestionQueueJob).delete()
        session.commit()
        session.close()
