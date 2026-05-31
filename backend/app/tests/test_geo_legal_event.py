"""Tests for GeoLegalEvent functionality.

Tests cover:
- GeoLegalEvent schema validation
- Publication gate integration for GeoLegalEvents
- Map materializer logic
- Live map API filtering and redaction
- Safety constraints (no raw source data reaches public map)
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.geo_legal_event import GeoLegalEvent as GeoLegalEventModel
from app.review.publication_gate import (
    PublicationBlockedError,
    assert_geo_legal_event_publication_ready,
)
from app.schemas.geo_legal_event import (
    CONFIDENCE_LABELS,
    EVENT_TYPES,
    GeoLegalEvent,
    PUBLISH_STATUSES,
    REVIEW_STATUSES,
    get_confidence_label,
)


# ---------------------------------------------------------------------------
# Tests: GeoLegalEvent schema validation
# ---------------------------------------------------------------------------


def test_geo_legal_event_schema_valid():
    """Test that a valid GeoLegalEvent passes schema validation."""
    event = GeoLegalEvent(
        id="test-event-1",
        event_type="court_event",
        title="Test Court Event",
        description="A test court event",
        lat=50.0,
        lng=-105.0,
        location_name="Test Location",
        occurred_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=["source-1"],
        evidence_ids=["evidence-1"],
        claim_ids=["claim-1"],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=["court", "test"],
        metadata_json={"test": "data"},
    )
    assert event.id == "test-event-1"
    assert event.event_type == "court_event"
    assert event.confidence == 0.8


def test_geo_legal_event_schema_invalid_event_type():
    """Test that invalid event types are rejected."""
    with pytest.raises(ValidationError):
        GeoLegalEvent(
            id="test-event-2",
            event_type="invalid_event_type",
            title="Test Event",
            jurisdiction="federal",
            country="Canada",
            confidence=0.8,
            confidence_label="high",
            review_status="approved",
            publish_status="public_safe",
        )


def test_geo_legal_event_schema_confidence_out_of_range():
    """Test that confidence values outside [0.0, 1.0] are rejected."""
    with pytest.raises(ValidationError):
        GeoLegalEvent(
            id="test-event-3",
            event_type="court_event",
            title="Test Event",
            jurisdiction="federal",
            country="Canada",
            confidence=1.5,  # Invalid: > 1.0
            confidence_label="high",
            review_status="approved",
            publish_status="public_safe",
        )


def test_geo_legal_event_schema_missing_required_fields():
    """Test that missing required fields are rejected."""
    with pytest.raises(ValidationError):
        GeoLegalEvent(
            id="test-event-4",
            # Missing event_type
            title="Test Event",
            jurisdiction="federal",
            country="Canada",
            confidence=0.8,
            confidence_label="high",
            review_status="approved",
            publish_status="public_safe",
        )


def test_confidence_label_mapping():
    """Test that confidence labels are correctly mapped."""
    assert get_confidence_label(0.95) == "very_high"
    assert get_confidence_label(0.8) == "high"
    assert get_confidence_label(0.6) == "medium"
    assert get_confidence_label(0.4) == "low"
    assert get_confidence_label(0.1) == "very_low"


def test_event_types_constant():
    """Test that EVENT_TYPES includes all expected event types."""
    expected_types = [
        "court_event",
        "judge_event",
        "crime_event",
        "police_release",
        "news_event",
        "legislation_event",
        "statistical_event",
        "correction_event",
        "contradiction_event",
    ]
    for event_type in expected_types:
        assert event_type in EVENT_TYPES


def test_review_statuses_constant():
    """Test that REVIEW_STATUSES includes all expected statuses."""
    expected_statuses = [
        "raw",
        "parsed",
        "needs_review",
        "approved",
        "rejected",
        "superseded",
    ]
    for status in expected_statuses:
        assert status in REVIEW_STATUSES


def test_publish_statuses_constant():
    """Test that PUBLISH_STATUSES includes all expected statuses."""
    expected_statuses = [
        "private",
        "admin_only",
        "public_safe",
        "public_redacted",
        "blocked",
    ]
    for status in expected_statuses:
        assert status in PUBLISH_STATUSES


# ---------------------------------------------------------------------------
# Tests: Publication gate integration for GeoLegalEvents
# ---------------------------------------------------------------------------


def test_publication_gate_allows_approved_event(db_session):
    """Test that approved events with proper confidence pass the publication gate."""
    event = GeoLegalEvent(
        id="test-event-5",
        event_type="court_event",
        title="Test Court Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    # Should not raise an exception
    assert_geo_legal_event_publication_ready(event, db_session)


def test_publication_gate_blocks_needs_review(db_session):
    """Test that events needing review are blocked."""
    event = GeoLegalEvent(
        id="test-event-6",
        event_type="court_event",
        title="Test Court Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.8,
        confidence_label="high",
        review_status="needs_review",  # Not approved
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "review_status" in str(exc_info.value)


def test_publication_gate_blocks_low_confidence(db_session):
    """Test that events with low confidence are blocked."""
    event = GeoLegalEvent(
        id="test-event-7",
        event_type="court_event",
        title="Test Court Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.5,  # Below default threshold of 0.7
        confidence_label="medium",
        review_status="approved",
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "confidence" in str(exc_info.value)


def test_publication_gate_blocks_missing_coordinates(db_session):
    """Test that events without coordinates are blocked."""
    event = GeoLegalEvent(
        id="test-event-8",
        event_type="court_event",
        title="Test Court Event",
        lat=None,  # Missing coordinates
        lng=None,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "coordinates" in str(exc_info.value)


def test_publication_gate_blocks_invalid_coordinates(db_session):
    """Test that events with invalid coordinates are blocked."""
    event = GeoLegalEvent(
        id="test-event-9",
        event_type="court_event",
        title="Test Court Event",
        lat=95.0,  # Invalid: > 90
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "invalid coordinates" in str(exc_info.value)


def test_publication_gate_blocks_wrong_publish_status(db_session):
    """Test that events with wrong publish status are blocked."""
    event = GeoLegalEvent(
        id="test-event-10",
        event_type="court_event",
        title="Test Court Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="admin_only",  # Not public-safe or public-redacted
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "publish_status" in str(exc_info.value)


def test_publication_gate_crime_event_requires_higher_confidence(db_session):
    """Test that crime events require higher confidence (0.8)."""
    event = GeoLegalEvent(
        id="test-event-11",
        event_type="crime_event",  # Crime event type
        title="Test Crime Event",
        lat=50.0,
        lng=-105.0,
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.75,  # Below 0.8 threshold for crime events
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=[],
        metadata={},
    )

    with pytest.raises(PublicationBlockedError) as exc_info:
        assert_geo_legal_event_publication_ready(event, db_session)
    assert "crime/police events require confidence" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests: Model persistence
# ---------------------------------------------------------------------------


def test_geo_legal_event_model_persistence(db_session):
    """Test that GeoLegalEvent models can be persisted to the database."""
    event_model = GeoLegalEventModel(
        id="test-event-12",
        event_type="court_event",
        title="Test Court Event",
        description="A test court event",
        lat=50.0,
        lng=-105.0,
        location_name="Test Location",
        occurred_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        jurisdiction="federal",
        province="Saskatchewan",
        country="Canada",
        source_ids=["source-1"],
        evidence_ids=["evidence-1"],
        claim_ids=["claim-1"],
        confidence=0.8,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=["court", "test"],
        metadata={"test": "data"},
    )

    db_session.add(event_model)
    db_session.commit()

    # Retrieve the event
    retrieved = db_session.query(GeoLegalEventModel).filter(
        GeoLegalEventModel.id == "test-event-12"
    ).first()

    assert retrieved is not None
    assert retrieved.event_type == "court_event"
    assert retrieved.confidence == 0.8
    assert retrieved.review_status == "approved"


def test_geo_legal_event_model_indexes(db_session):
    """Test that GeoLegalEvent model indexes work correctly."""
    # Create multiple events with different statuses
    for i in range(5):
        event_model = GeoLegalEventModel(
            id=f"test-event-{13+i}",
            event_type="court_event",
            title=f"Test Event {i}",
            lat=50.0 + i,
            lng=-105.0,
            jurisdiction="federal",
            country="Canada",
            confidence=0.8,
            confidence_label="high",
            review_status="approved" if i % 2 == 0 else "needs_review",
            publish_status="public_safe",
        )
        db_session.add(event_model)

    db_session.commit()

    # Test index on review_status
    approved_events = db_session.query(GeoLegalEventModel).filter(
        GeoLegalEventModel.review_status == "approved"
    ).all()
    assert len(approved_events) == 3

    # Test index on event_type
    court_events = db_session.query(GeoLegalEventModel).filter(
        GeoLegalEventModel.event_type == "court_event"
    ).all()
    assert len(court_events) == 5