"""Tests for source enablement workflow (Phase 13).

Tests source enablement, validation, and rollback.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry
from app.ingestion.source_enablement import (
    enable_source,
    disable_source,
    validate_source_before_enable,
    get_next_source_to_enable,
    rollback_source_enablement,
    batch_enable_sources,
)
from app.db.session import engine


class TestSourceEnablement:
    """Test source enablement logic."""

    def test_enable_source_success(self, db_session):
        """Test successful source enablement."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=False,
            lifecycle_state="runnable_disabled",
            parser="test_parser",
            parser_version="1.0",
            allowed_domains=["example.com"],
            base_url="https://example.com",
            automation_status="machine_ready_disabled",
            public_record_authority="official",
            terms_url="https://example.com/terms",
        )
        db_session.add(registry)
        db_session.commit()

        success, message = enable_source("test_source", "test_user", db_session)

        assert success is True
        assert "enabled successfully" in message.lower()

        db_session.refresh(registry)
        assert registry.is_active is True

    def test_enable_source_with_blockers(self, db_session):
        """Test that sources with blockers cannot be enabled."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=False,
            lifecycle_state="deprecated",
            parser="test_parser",
            parser_version="1.0",
            allowed_domains=["example.com"],
            base_url="https://example.com",
            public_record_authority="official",
            terms_url="https://example.com/terms",
        )
        db_session.add(registry)
        db_session.commit()

        success, message = enable_source("test_source", "test_user", db_session)

        assert success is False
        assert "blocked" in message.lower()

    def test_disable_source(self, db_session):
        """Test source disablement."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=True,
            lifecycle_state="runnable",
        )
        db_session.add(registry)
        db_session.commit()

        success, message = disable_source("test_source", "test_user", "test reason", db_session)

        assert success is True

        db_session.refresh(registry)
        assert registry.is_active is False


class TestSourceValidation:
    """Test source validation before enablement."""

    def test_validate_valid_source(self, db_session):
        """Test validation of a valid source."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=False,
            parser="test_parser",
            parser_version="1.0",
            allowed_domains=["example.com"],
            base_url="https://example.com",
            automation_status="machine_ready_disabled",
            public_record_authority="official",
            terms_url="https://example.com/terms",
        )
        db_session.add(registry)
        db_session.commit()

        is_valid, errors = validate_source_before_enable("test_source", db_session)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_missing_required_fields(self, db_session):
        """Test that missing required fields fail validation."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=False,
            # Missing required fields
        )
        db_session.add(registry)
        db_session.commit()

        is_valid, errors = validate_source_before_enable("test_source", db_session)

        assert is_valid is False
        assert len(errors) > 0


class TestNextSourceToEnable:
    """Test getting next source candidate for enablement."""

    def test_get_next_source_to_enable(self, db_session):
        """Test getting the next source to enable."""
        # Create multiple disabled sources
        for i in range(3):
            registry = SourceRegistry(
                source_key=f"source_{i}",
                source_name=f"Source {i}",
                source_tier="court_record" if i == 0 else "news_only_context",
                source_class="machine_ingest",
                is_active=False,
                parser="test_parser",
                parser_version="1.0",
                allowed_domains=["example.com"],
                base_url="https://example.com",
                automation_status="machine_ready_disabled",
                public_record_authority="official",
                terms_url="https://example.com/terms",
                health_score=0.5 + (i * 0.1),
            )
            db_session.add(registry)
        db_session.commit()

        next_source = get_next_source_to_enable(db_session)

        assert next_source is not None
        # Should return the highest tier source
        assert next_source.source_tier == "court_record"

    def test_get_next_source_none_available(self, db_session):
        """Test when no sources are available for enablement."""
        # Ensure test isolation from prior suite inserts.
        db_session.query(SourceRegistry).delete()
        db_session.commit()

        # No disabled sources
        next_source = get_next_source_to_enable(db_session)
        assert next_source is None


class TestRollbackEnablement:
    """Test rollback of source enablement."""

    def test_rollback_enablement(self, db_session):
        """Test rollback of source enablement."""
        registry = SourceRegistry(
            source_key="test_source",
            source_name="Test Source",
            source_tier="court_record",
            source_class="machine_ingest",
            is_active=True,
            lifecycle_state="runnable",
        )
        db_session.add(registry)
        db_session.commit()

        success, message = rollback_source_enablement("test_source", "test rollback", db_session)

        assert success is True

        db_session.refresh(registry)
        assert registry.is_active is False


class TestBatchEnablement:
    """Test batch source enablement."""

    def test_batch_enable_sources(self, db_session):
        """Test enabling multiple sources in batch."""
        # Create multiple sources
        for i in range(3):
            registry = SourceRegistry(
                source_key=f"source_{i}",
                source_name=f"Source {i}",
                source_tier="court_record",
                source_class="machine_ingest",
                is_active=False,
                parser="test_parser",
                parser_version="1.0",
                allowed_domains=["example.com"],
                base_url="https://example.com",
                automation_status="machine_ready_disabled",
                public_record_authority="official",
                terms_url="https://example.com/terms",
            )
            db_session.add(registry)
        db_session.commit()

        results = batch_enable_sources(["source_0", "source_1"], "test_user", db_session)

        assert len(results) == 2
        assert results["source_0"][0] is True
        assert results["source_1"][0] is True


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
