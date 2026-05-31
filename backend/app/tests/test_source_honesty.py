"""Tests for source honesty tracking (Phase 12).

Tests source reliability tracking and quality metrics.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry
from app.ingestion.source_honesty import (
    calculate_source_honesty_score,
    update_source_reliability_metrics,
    get_source_quality_metrics,
    get_top_reliable_sources,
    flag_unreliable_source,
)
from app.db.session import engine


class TestSourceHonestyScore:
    """Test source honesty score calculation."""

    def test_honesty_score_from_health_score(self, db_session):
        """Test that honesty score is based on health score."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,
        )
        db_session.add(registry)
        db_session.commit()

        score = calculate_source_honesty_score("test_source", db_session)
        assert score >= 0.0
        assert score <= 1.0

    def test_recent_error_reduces_honesty_score(self, db_session):
        """Test that recent errors reduce honesty score."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,
            last_error_at=datetime.now(timezone.utc),
        )
        db_session.add(registry)
        db_session.commit()

        score = calculate_source_honesty_score("test_source", db_session)
        assert score < 0.8  # Should be reduced due to recent error

    def test_old_error_has_less_impact(self, db_session):
        """Test that old errors have less impact on honesty score."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,
            last_error_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db_session.add(registry)
        db_session.commit()

        score = calculate_source_honesty_score("test_source", db_session)
        # Should have less penalty than recent error
        assert score >= 0.7


class TestReliabilityMetrics:
    """Test reliability metrics update."""

    def test_update_reliability_metrics_success(self, db_session):
        """Test updating reliability metrics with success."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.5,
        )
        db_session.add(registry)
        db_session.commit()

        update_source_reliability_metrics("test_source", 90, 10, db_session)

        db_session.refresh(registry)
        assert registry.health_score >= 0.5  # Should increase due to high success rate

    def test_update_reliability_metrics_failure(self, db_session):
        """Test updating reliability metrics with failure."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,
        )
        db_session.add(registry)
        db_session.commit()

        update_source_reliability_metrics("test_source", 10, 90, db_session)

        db_session.refresh(registry)
        assert registry.health_score < 0.8  # Should decrease due to low success rate


class TestQualityMetrics:
    """Test quality metrics retrieval."""

    def test_get_quality_metrics(self, db_session):
        """Test getting quality metrics for a source."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,
            last_successful_fetch=datetime.now(timezone.utc),
        )
        db_session.add(registry)
        db_session.commit()

        metrics = get_source_quality_metrics("test_source", db_session)

        assert metrics["source_key"] == "test_source"
        assert metrics["source_name"] == "Test Source"
        assert "honesty_score" in metrics
        assert "health_score" in metrics
        assert "uptime_percentage" in metrics

    def test_get_quality_metrics_nonexistent_source(self, db_session):
        """Test getting quality metrics for nonexistent source."""
        metrics = get_source_quality_metrics("nonexistent_source", db_session)
        assert "error" in metrics


class TestTopReliableSources:
    """Test top reliable sources retrieval."""

    def test_get_top_reliable_sources(self, db_session):
        """Test getting top reliable sources."""
        # Create multiple sources with different health scores
        for i in range(3):
            registry = SourceRegistry(
                source_key=f"source_{i}",
                source_name=f"Source {i}",
                source_tier="court_record",
                is_active=True,
                health_score=0.5 + (i * 0.2),
            )
            db_session.add(registry)
        db_session.commit()

        top_sources = get_top_reliable_sources(db_session, limit=2)

        assert len(top_sources) == 2
        # Should be sorted by honesty score descending
        assert top_sources[0]["honesty_score"] >= top_sources[1]["honesty_score"]


class TestUnreliableSourceFlagging:
    """Test unreliable source flagging."""

    def test_flag_unreliable_source(self, db_session):
        """Test flagging an unreliable source."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.3,  # Low health score
        )
        db_session.add(registry)
        db_session.commit()

        result = flag_unreliable_source("test_source", db_session)

        db_session.refresh(registry)
        assert result is True
        assert registry.is_active is False
        assert "unreliable" in registry.last_error.lower()

    def test_do_not_flag_reliable_source(self, db_session):
        """Test that reliable sources are not flagged."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            is_active=True,
            health_score=0.8,  # High health score
        )
        db_session.add(registry)
        db_session.commit()

        result = flag_unreliable_source("test_source", db_session)

        db_session.refresh(registry)
        assert result is False
        assert registry.is_active is True


@pytest.fixture
def db_session():
    """Create an isolated database session for testing."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, future=True)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not getattr(trans._parent, "nested", False):
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        transaction.rollback()
        connection.close()
