"""Tests for reviewer dashboard metrics (Phase 16).

Tests review metrics, queue metrics, and workflow health.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.models.entities import ReviewActionLog, CrimeIncident
from app.review.dashboard_metrics import (
    get_reviewer_metrics,
    get_queue_metrics,
    get_review_trend,
    get_top_reviewers,
    get_workflow_health,
)
from app.db.session import engine
from sqlalchemy.orm import Session


class TestReviewerMetrics:
    """Test reviewer performance metrics."""

    def test_get_reviewer_metrics_no_reviews(self, db_session):
        """Test metrics when no reviews exist."""
        metrics = get_reviewer_metrics(db_session, reviewer_id="__none__", days=30)

        assert metrics["total_reviews"] == 0
        assert metrics["approved_count"] == 0
        assert metrics["rejected_count"] == 0
        assert metrics["approval_rate"] == 0.0

    def test_get_reviewer_metrics_with_reviews(self, db_session):
        """Test metrics with review actions."""
        # Add review action
        log = ReviewActionLog(
            review_item_id=1,
            actor="reviewer1",
            action="approved",
            before_json={"status": "pending"},
            after_json={"status": "approved"},
        )
        db_session.add(log)
        db_session.commit()

        metrics = get_reviewer_metrics(db_session, reviewer_id="reviewer1", days=30)

        assert metrics["total_reviews"] == 1
        assert metrics["approved_count"] == 1


class TestQueueMetrics:
    """Test review queue metrics."""

    def test_get_queue_metrics_empty(self, db_session):
        """Test queue metrics returns a valid shape when no test fixtures are added."""
        metrics = get_queue_metrics(db_session)

        assert metrics["total_pending"] >= 0
        assert metrics["pending_events"] >= 0
        assert metrics["pending_incidents"] >= 0

    def test_get_queue_metrics_with_pending(self, db_session):
        """Test queue metrics with pending items."""
        before = get_queue_metrics(db_session)

        incident = CrimeIncident(
            source_name="test_source",
            incident_type="theft",
            incident_category="property",
            review_status="pending_review",
        )
        db_session.add(incident)
        db_session.commit()

        metrics = get_queue_metrics(db_session)

        assert metrics["pending_incidents"] >= before["pending_incidents"] + 1
        assert metrics["total_pending"] >= before["total_pending"] + 1


class TestReviewTrend:
    """Test review trend data."""

    def test_get_review_trend(self, db_session):
        """Test getting review trend over time."""
        trend = get_review_trend(db_session, days=30, bucket_days=7)

        assert len(trend) > 0
        assert "period_start" in trend[0]
        assert "period_end" in trend[0]
        assert "review_count" in trend[0]


class TestTopReviewers:
    """Test top reviewers ranking."""

    def test_get_top_reviewers_empty(self, db_session):
        """Test top reviewers response shape when no fixtures are added."""
        reviewers = get_top_reviewers(db_session, days=30, limit=10)

        assert isinstance(reviewers, list)

    def test_get_top_reviewers_with_activity(self, db_session):
        """Test top reviewers with review activity."""
        # Add review actions for different reviewers
        log1 = ReviewActionLog(
            review_item_id=1,
            actor="reviewer1",
            action="approved",
            before_json={"status": "pending"},
            after_json={"status": "approved"},
        )
        db_session.add(log1)

        log2 = ReviewActionLog(
            review_item_id=2,
            actor="reviewer2",
            action="approved",
            before_json={"status": "pending"},
            after_json={"status": "approved"},
        )
        db_session.add(log2)
        db_session.commit()

        reviewers = get_top_reviewers(db_session, days=30, limit=10)

        assert len(reviewers) >= 1
        assert "reviewer_id" in reviewers[0]
        assert "review_count" in reviewers[0]


class TestWorkflowHealth:
    """Test workflow health metrics."""

    def test_get_workflow_health(self, db_session):
        """Test getting overall workflow health."""
        health = get_workflow_health(db_session)

        assert "queue_size" in health
        assert "recent_activity_24h" in health
        assert "health_score" in health
        assert "healthy" in health
        assert 0.0 <= health["health_score"] <= 1.0


@pytest.fixture
def db_session():
    """Create an isolated database session for testing."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
