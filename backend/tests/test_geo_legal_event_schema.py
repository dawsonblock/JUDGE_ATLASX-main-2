"""Tests for GeoLegalEvent schema."""
import pytest
from datetime import datetime, timezone
from app.schemas.geo_legal_event import GeoLegalEvent, get_confidence_label


def test_geo_legal_event_creation():
    """Test creating a GeoLegalEvent instance."""
    event = GeoLegalEvent(
        id="test-123",
        event_type="court_event",
        title="Test Event",
        description="Test description",
        lat=45.4215,
        lng=-75.6972,
        location_name="Ottawa",
        occurred_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        jurisdiction="federal",
        province="ON",
        country="Canada",
        source_ids=["source-1"],
        evidence_ids=["evidence-1"],
        claim_ids=["claim-1"],
        confidence=0.85,
        confidence_label="high",
        review_status="approved",
        publish_status="public_safe",
        tags=["court", "test"],
        metadata={"test": "data"},
    )

    assert event.id == "test-123"
    assert event.event_type == "court_event"
    assert event.confidence == 0.85
    assert event.review_status == "approved"


def test_get_confidence_label():
    """Test confidence label mapping."""
    assert get_confidence_label(0.95) == "very_high"
    assert get_confidence_label(0.85) == "high"
    assert get_confidence_label(0.6) == "medium"
    assert get_confidence_label(0.4) == "low"
    assert get_confidence_label(0.1) == "very_low"


def test_geo_legal_event_optional_fields():
    """Test GeoLegalEvent with optional fields as None."""
    event = GeoLegalEvent(
        id="test-456",
        event_type="crime_event",
        title="Test Crime",
        description=None,
        lat=None,
        lng=None,
        location_name=None,
        occurred_at=None,
        published_at=None,
        jurisdiction="provincial",
        province="BC",
        country="Canada",
        source_ids=[],
        evidence_ids=[],
        claim_ids=[],
        confidence=0.5,
        confidence_label="medium",
        review_status="needs_review",
        publish_status="admin_only",
        tags=[],
        metadata={},
    )

    assert event.description is None
    assert event.lat is None
    assert event.lng is None
    assert event.source_ids == []
