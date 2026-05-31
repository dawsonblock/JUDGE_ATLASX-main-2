"""Tests for event ingestion (Phase 9).

Tests event data ingestion, validation, and linking to entities.
"""

import pytest
from datetime import date

from app.models.entities import Event, Case, Court, Location, Judge, Defendant
from app.ingestion.event_ingestion import (
    ingest_event,
    link_event_to_defendant,
    validate_event_data,
)


class TestEventIngestion:
    """Test event ingestion logic."""

    def test_ingest_event_success(self, db_session):
        """Test successful event ingestion."""
        # Create required entities
        location = Location(
            name="Test Courthouse",
            location_type="courthouse",
            latitude=37.7749,
            longitude=-122.4194,
        )
        court = Court(
            name="Superior Court",
            location_id=location.id if location.id else None,
            jurisdiction="CA",
        )
        db_session.add_all([location, court])
        db_session.flush()

        case = Case(
            case_number="TEST-2024-001",
            court_id=court.id,
            jurisdiction="CA",
        )
        db_session.add(case)
        db_session.commit()

        event_data = {
            "event_id": "test_event_001",
            "case_id": case.id,
            "court_id": court.id,
            "event_type": "hearing",
            "title": "Test Hearing",
            "summary": "Test hearing summary",
            "decision_date": "2024-01-15",
        }

        event = ingest_event(event_data, "test_source", db_session)

        assert event.event_id == "test_event_001"
        assert event.event_type == "hearing"
        assert event.title == "Test Hearing"

    def test_ingest_event_missing_required_field(self, db_session):
        """Test that missing required fields raise ValueError."""
        event_data = {
            "event_id": "test_event_001",
            "case_id": 1,
            "court_id": 1,
            # Missing event_type, title, summary
        }

        with pytest.raises(ValueError) as exc_info:
            ingest_event(event_data, "test_source", db_session)

        assert "Missing required field" in str(exc_info.value)

    def test_ingest_event_duplicate(self, db_session):
        """Test that duplicate events are not created."""
        # Create required entities
        location = Location(
            name="Test Courthouse",
            location_type="courthouse",
            latitude=37.7749,
            longitude=-122.4194,
        )
        court = Court(
            name="Superior Court",
            location_id=location.id if location.id else None,
            jurisdiction="CA",
        )
        db_session.add_all([location, court])
        db_session.flush()

        case = Case(
            case_number="TEST-2024-001",
            court_id=court.id,
            jurisdiction="CA",
        )
        db_session.add(case)
        db_session.commit()

        event_data = {
            "event_id": "test_event_001",
            "case_id": case.id,
            "court_id": court.id,
            "event_type": "hearing",
            "title": "Test Hearing",
            "summary": "Test hearing summary",
        }

        # Ingest first time
        event1 = ingest_event(event_data, "test_source", db_session)

        # Ingest second time (should return existing)
        event2 = ingest_event(event_data, "test_source", db_session)

        assert event1.id == event2.id


class TestEventLinking:
    """Test event-to-defendant linking."""

    def test_link_event_to_defendant(self, db_session):
        """Test linking event to defendant."""
        # Create event
        location = Location(
            name="Test Courthouse",
            location_type="courthouse",
            latitude=37.7749,
            longitude=-122.4194,
        )
        court = Court(
            name="Superior Court",
            location_id=location.id if location.id else None,
            jurisdiction="CA",
        )
        db_session.add_all([location, court])
        db_session.flush()

        case = Case(
            case_number="TEST-2024-001",
            court_id=court.id,
            jurisdiction="CA",
        )
        db_session.add(case)
        db_session.flush()

        event = Event(
            event_id="test_event_001",
            case_id=case.id,
            court_id=court.id,
            primary_location_id=location.id if location.id else None,
            event_type="hearing",
            title="Test Hearing",
            summary="Test summary",
        )
        db_session.add(event)
        db_session.flush()

        # Create defendant
        defendant = Defendant(
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(defendant)
        db_session.commit()

        # Link event to defendant
        result = link_event_to_defendant(event.id, defendant.id, db_session)

        assert result is True

    def test_link_event_to_defendant_duplicate(self, db_session):
        """Test that duplicate links are not created."""
        # Create event and defendant
        location = Location(
            name="Test Courthouse",
            location_type="courthouse",
            latitude=37.7749,
            longitude=-122.4194,
        )
        court = Court(
            name="Superior Court",
            location_id=location.id if location.id else None,
            jurisdiction="CA",
        )
        db_session.add_all([location, court])
        db_session.flush()

        case = Case(
            case_number="TEST-2024-001",
            court_id=court.id,
            jurisdiction="CA",
        )
        db_session.add(case)
        db_session.flush()

        event = Event(
            event_id="test_event_001",
            case_id=case.id,
            court_id=court.id,
            primary_location_id=location.id if location.id else None,
            event_type="hearing",
            title="Test Hearing",
            summary="Test summary",
        )
        db_session.add(event)
        db_session.flush()

        defendant = Defendant(
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(defendant)
        db_session.commit()

        # Link first time
        result1 = link_event_to_defendant(event.id, defendant.id, db_session)

        # Link second time (should return False)
        result2 = link_event_to_defendant(event.id, defendant.id, db_session)

        assert result1 is True
        assert result2 is False


class TestEventValidation:
    """Test event data validation."""

    def test_validate_valid_event_data(self):
        """Test validation of valid event data."""
        event_data = {
            "event_id": "test_event_001",
            "case_id": 1,
            "court_id": 1,
            "event_type": "hearing",
            "title": "Test Hearing",
            "summary": "Test summary",
        }

        result = validate_event_data(event_data)

        assert len(result["errors"]) == 0
        assert len(result["warnings"]) > 0  # Should have warnings for optional fields

    def test_validate_missing_required_field(self):
        """Test that missing required fields produce errors."""
        event_data = {
            "event_id": "test_event_001",
            # Missing case_id, court_id, event_type, title, summary
        }

        result = validate_event_data(event_data)

        assert len(result["errors"]) > 0
        assert any("Missing required field" in error for error in result["errors"])

    def test_validate_invalid_date_format(self):
        """Test that invalid date formats produce errors."""
        event_data = {
            "event_id": "test_event_001",
            "case_id": 1,
            "court_id": 1,
            "event_type": "hearing",
            "title": "Test Hearing",
            "summary": "Test summary",
            "decision_date": "invalid-date",
        }

        result = validate_event_data(event_data)

        assert len(result["errors"]) > 0
        assert any("Invalid date format" in error for error in result["errors"])

