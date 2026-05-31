"""Tests for Phase 4: Source Stability & Recovery"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.ingestion.recovery_strategies import (
    classify_error,
    calculate_backoff_seconds,
    should_retry_ingestion,
    is_health_degraded,
    get_health_status_label,
    is_timeout_error,
    is_rate_limit_error,
    is_service_unavailable_error,
    is_connection_error,
    ErrorCategory,
    RecoveryStrategy,
)
from app.ingestion.dead_letter_queue import DeadLetterQueue
from app.ingestion.statuses import FAILED, QUARANTINED, COMPLETED, RUNNING
from app.models.entities import IngestionRun, SourceRegistry


class TestErrorClassification:
    """Tests for error classification logic."""

    def test_classify_transient_timeout_error(self):
        """Timeout errors should be classified as transient."""
        classification = classify_error("Request timeout after 30 seconds")
        assert classification.category == ErrorCategory.TRANSIENT
        assert classification.retriable is True
        assert classification.strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF

    def test_classify_transient_connection_reset(self):
        """Connection reset errors should be transient."""
        classification = classify_error("Connection reset by peer")
        assert classification.category == ErrorCategory.TRANSIENT
        assert classification.retriable is True

    def test_classify_transient_rate_limit(self):
        """HTTP 429 rate limit should be transient."""
        classification = classify_error("HTTP 429 Too Many Requests")
        assert classification.category == ErrorCategory.TRANSIENT
        assert classification.retriable is True

    def test_classify_transient_service_unavailable(self):
        """HTTP 503 service unavailable should be transient."""
        classification = classify_error("HTTP 503 Service Unavailable")
        assert classification.category == ErrorCategory.TRANSIENT
        assert classification.retriable is True

    def test_classify_permanent_authentication_error(self):
        """401 Unauthorized should be permanent."""
        classification = classify_error("HTTP 401 Unauthorized: invalid API key")
        assert classification.category == ErrorCategory.PERMANENT
        assert classification.retriable is False
        assert classification.strategy == RecoveryStrategy.QUARANTINE_FOR_REVIEW

    def test_classify_permanent_forbidden_error(self):
        """403 Forbidden should be permanent."""
        classification = classify_error("HTTP 403 Forbidden: access denied")
        assert classification.category == ErrorCategory.PERMANENT
        assert classification.retriable is False

    def test_classify_permanent_contract_violation(self):
        """Contract violation should be permanent."""
        classification = classify_error("Adapter contract violation: no_raw_content")
        assert classification.category == ErrorCategory.PERMANENT
        assert classification.retriable is False

    def test_classify_permanent_schema_mismatch(self):
        """Schema validation errors should be permanent."""
        classification = classify_error("Field validation error: required field missing")
        assert classification.category == ErrorCategory.PERMANENT
        assert classification.retriable is False

    def test_classify_permanent_parser_version_mismatch(self):
        """Parser version mismatch should be permanent."""
        classification = classify_error("Parser version mismatch: expected 2.0, got 1.5")
        assert classification.category == ErrorCategory.PERMANENT
        assert classification.retriable is False

    def test_classify_unknown_error(self):
        """Unknown error patterns should default to quarantine."""
        classification = classify_error("Something weird happened")
        assert classification.category == ErrorCategory.UNKNOWN
        assert classification.retriable is False

    def test_classify_empty_error_message(self):
        """Empty error message should result in unknown classification."""
        classification = classify_error(None)
        assert classification.category == ErrorCategory.UNKNOWN
        assert classification.retriable is False


class TestExponentialBackoff:
    """Tests for exponential backoff calculation."""

    def test_backoff_attempt_zero(self):
        """First attempt (attempt 0) should be ~60 seconds."""
        backoff = calculate_backoff_seconds(attempt=0, base_seconds=60, max_seconds=3600)
        # Should be 60 + jitter (jitter is random, just verify it's in reasonable range)
        assert 60 <= backoff <= 120

    def test_backoff_attempt_one(self):
        """Second attempt (attempt 1) should be ~120 seconds."""
        backoff = calculate_backoff_seconds(attempt=1, base_seconds=60, max_seconds=3600)
        # Should be 120 + jitter
        assert 120 <= backoff <= 240

    def test_backoff_attempt_two(self):
        """Third attempt should be ~240 seconds."""
        backoff = calculate_backoff_seconds(attempt=2, base_seconds=60, max_seconds=3600)
        # Should be 240 + jitter
        assert 240 <= backoff <= 480

    def test_backoff_respects_max_cap(self):
        """Backoff should never exceed max_seconds."""
        backoff = calculate_backoff_seconds(
            attempt=10, base_seconds=60, max_seconds=3600
        )
        assert backoff <= 3600

    def test_backoff_with_custom_base(self):
        """Should work with custom base duration."""
        backoff = calculate_backoff_seconds(attempt=0, base_seconds=30, max_seconds=3600)
        # Should be 30 + jitter
        assert 30 <= backoff <= 33


class TestShouldRetryIngestion:
    """Tests for retry decision logic."""

    def test_retry_transient_error_first_attempt(self, db_session: Session):
        """Transient error on first attempt should be retriable."""
        run = IngestionRun(
            source_name="test_source",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 503 Service Unavailable"],
            error_count=1,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        should_retry, reason = should_retry_ingestion(run, max_retries=3)
        assert should_retry is True
        assert "Transient error" in reason

    def test_no_retry_permanent_error(self, db_session: Session):
        """Permanent errors should not be retriable."""
        run = IngestionRun(
            source_name="test_source",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 401 Unauthorized"],
            error_count=1,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        should_retry, reason = should_retry_ingestion(run, max_retries=3)
        assert should_retry is False
        assert "Permanent error" in reason

    def test_no_retry_max_attempts_exceeded(self, db_session: Session):
        """Should not retry after max attempts reached."""
        run = IngestionRun(
            source_name="test_source",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 503 Service Unavailable"],
            error_count=1,
            retry_count=3,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        should_retry, reason = should_retry_ingestion(run, max_retries=3)
        assert should_retry is False
        assert "Max retries" in reason

    def test_no_retry_no_errors(self, db_session: Session):
        """No errors recorded should not retry."""
        run = IngestionRun(
            source_name="test_source",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=None,
            error_count=0,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        should_retry, reason = should_retry_ingestion(run, max_retries=3)
        assert should_retry is False


class TestHealthDegradation:
    """Tests for health score monitoring."""

    def test_is_health_degraded_above_threshold(self):
        """Health above threshold should not be degraded."""
        assert is_health_degraded(0.8) is False
        assert is_health_degraded(1.0) is False

    def test_is_health_degraded_below_threshold(self):
        """Health below threshold should be degraded."""
        assert is_health_degraded(0.5) is True
        assert is_health_degraded(0.4) is True
        assert is_health_degraded(0.0) is True

    def test_health_status_label_healthy(self):
        """High health should be labeled healthy."""
        assert get_health_status_label(1.0) == "healthy"
        assert get_health_status_label(0.9) == "healthy"
        assert get_health_status_label(0.8) == "healthy"

    def test_health_status_label_degraded(self):
        """Medium health should be labeled degraded."""
        assert get_health_status_label(0.7) == "degraded"
        assert get_health_status_label(0.6) == "degraded"

    def test_health_status_label_critical(self):
        """Low health should be labeled critical."""
        assert get_health_status_label(0.4) == "critical"
        assert get_health_status_label(0.0) == "critical"

    def test_health_status_label_none(self):
        """None health should default to healthy (1.0)."""
        assert get_health_status_label(None) == "healthy"


class TestTransientErrorDetection:
    """Tests for individual transient error helpers."""

    def test_is_timeout_error(self):
        """Should detect timeout errors."""
        assert is_timeout_error("Request timeout after 30 seconds") is True
        assert is_timeout_error("Socket timeout") is True
        assert is_timeout_error("Deadline exceeded") is True
        assert is_timeout_error("Connection refused") is False

    def test_is_rate_limit_error(self):
        """Should detect rate limit errors."""
        assert is_rate_limit_error("HTTP 429 Too Many Requests") is True
        assert is_rate_limit_error("Rate limit exceeded") is True
        assert is_rate_limit_error("Quota exceeded") is True
        assert is_rate_limit_error("HTTP 401 Unauthorized") is False

    def test_is_service_unavailable_error(self):
        """Should detect service unavailability."""
        assert is_service_unavailable_error("HTTP 503 Service Unavailable") is True
        assert is_service_unavailable_error("HTTP 502 Bad Gateway") is True
        assert is_service_unavailable_error("Service unavailable") is True
        assert is_service_unavailable_error("HTTP 401 Unauthorized") is False

    def test_is_connection_error(self):
        """Should detect connection errors."""
        assert is_connection_error("Connection reset by peer") is True
        assert is_connection_error("Connection refused") is True
        assert is_connection_error("Network unreachable") is True
        assert is_connection_error("Timeout") is False


class TestDeadLetterQueue:
    """Tests for dead-letter queue operations."""

    def test_list_quarantined_runs_empty(self, db_session: Session):
        """Should return empty list when no quarantined runs."""
        # Clean up any previous test data
        db_session.query(IngestionRun).filter(
            IngestionRun.status.in_([QUARANTINED, FAILED])
        ).delete()
        db_session.commit()

        dlq = DeadLetterQueue(db_session)
        runs = dlq.list_quarantined_runs()
        assert runs == []

    def test_list_quarantined_runs_filters_by_source(self, db_session: Session):
        """Should filter quarantined runs by source."""
        run1 = IngestionRun(
            source_name="source1",
            started_at=datetime.now(timezone.utc),
            status=QUARANTINED,
            errors=["Test error"],
        )
        run2 = IngestionRun(
            source_name="source2",
            started_at=datetime.now(timezone.utc),
            status=QUARANTINED,
            errors=["Test error"],
        )
        db_session.add_all([run1, run2])
        db_session.commit()

        dlq = DeadLetterQueue(db_session)
        runs = dlq.list_quarantined_runs(source_key="source1")
        assert len(runs) == 1
        assert runs[0]["source_name"] == "source1"

    def test_classify_dead_letter_transient(self, db_session: Session):
        """Should classify transient errors correctly."""
        run = IngestionRun(
            source_name="test",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 503 Service Unavailable"],
        )
        db_session.add(run)
        db_session.commit()

        dlq = DeadLetterQueue(db_session)
        classification = dlq.classify_dead_letter(run)
        assert classification["error_category"] == "transient"
        assert classification["retriable"] is True
        assert classification["suggested_action"] == "auto_retry"

    def test_classify_dead_letter_permanent(self, db_session: Session):
        """Should classify permanent errors correctly."""
        run = IngestionRun(
            source_name="test",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 401 Unauthorized"],
        )
        db_session.add(run)
        db_session.commit()

        dlq = DeadLetterQueue(db_session)
        classification = dlq.classify_dead_letter(run)
        assert classification["error_category"] == "permanent"
        assert classification["retriable"] is False
        assert classification["suggested_action"] == "manual_intervention"

    def test_schedule_retry(self, db_session: Session):
        """Should schedule a retry for a transient error."""
        run = IngestionRun(
            source_name="test",
            started_at=datetime.now(timezone.utc),
            status=QUARANTINED,
            errors=["HTTP 503 Service Unavailable"],
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        dlq = DeadLetterQueue(db_session)
        success = dlq.schedule_retry(run.id)
        assert success is True

        # Verify retry_count incremented
        db_session.refresh(run)
        assert run.retry_count == 1

    def test_schedule_retry_fails_for_permanent_error(self, db_session: Session):
        """Should not schedule retry for permanent errors."""
        run = IngestionRun(
            source_name="test",
            started_at=datetime.now(timezone.utc),
            status=QUARANTINED,
            errors=["HTTP 401 Unauthorized"],
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        dlq = DeadLetterQueue(db_session)
        success = dlq.schedule_retry(run.id)
        assert success is False

    def test_get_recovery_summary(self, db_session: Session):
        """Should generate recovery summary stats."""
        # Clean up any previous test data
        db_session.query(IngestionRun).filter(
            IngestionRun.status.in_([QUARANTINED, FAILED])
        ).delete()
        db_session.commit()

        run1 = IngestionRun(
            source_name="source1",
            started_at=datetime.now(timezone.utc),
            status=QUARANTINED,
            errors=["HTTP 503 Service Unavailable"],
        )
        run2 = IngestionRun(
            source_name="source2",
            started_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 401 Unauthorized"],
        )
        db_session.add_all([run1, run2])
        db_session.commit()

        dlq = DeadLetterQueue(db_session)
        summary = dlq.get_recovery_summary()
        assert summary["total_quarantined"] == 2
        assert summary["failed_runs"] == 1
        assert summary["quarantined_runs"] == 1
        assert len(summary["quarantined_by_source"]) == 2


class TestPhase4Integration:
    """Integration tests for Phase 4 components."""

    def test_ingestion_run_has_recovery_fields(self):
        """IngestionRun should have Phase 4 fields."""
        run = IngestionRun(
            source_name="test",
            started_at=datetime.now(timezone.utc),
            status=RUNNING,
        )
        # Should not raise AttributeError
        assert run.retry_count is None
        assert run.scheduled_retry_at is None
        assert run.recovery_classification is None
        assert run.last_error_at is None

    def test_recovery_workflow_end_to_end(self, db_session: Session):
        """End-to-end recovery workflow."""
        # 1. Create a failed run with transient error
        run = IngestionRun(
            source_name="courtlistener",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status=FAILED,
            errors=["HTTP 503 Service Unavailable"],
            error_count=1,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        # 2. Classify error
        classification = classify_error(run.errors[0])
        assert classification.retriable is True

        # 3. Decide on retry
        should_retry, reason = should_retry_ingestion(run, max_retries=3)
        assert should_retry is True

        # 4. Schedule retry via DLQ
        dlq = DeadLetterQueue(db_session)
        retry_scheduled = dlq.schedule_retry(run.id)
        assert retry_scheduled is True

        # 5. Verify retry was scheduled
        db_session.refresh(run)
        assert run.retry_count == 1
        assert run.scheduled_retry_at is not None
