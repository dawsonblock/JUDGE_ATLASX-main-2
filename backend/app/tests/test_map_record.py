"""Tests for map record trust-field population in api.routes.map_record."""

from fastapi import HTTPException
import pytest
from unittest.mock import MagicMock, patch

from app.api.routes.map_record import _court_event_detail, _incident_detail
from app.policies.publication_policy import PublicationDecision


def _make_event(**overrides):
    ev = MagicMock()
    ev.event_id = "EVT-001"
    ev.title = "Test hearing"
    ev.summary = "A routine hearing."
    ev.event_type = "hearing"
    ev.event_subtype = None
    ev.decision_date = None
    ev.judge = None
    ev.court = None
    ev.case = None
    ev.primary_location = None
    ev.source_links = []
    ev.review_status = "verified"
    ev.reviewed_at = None
    ev.reviewed_by = None
    ev.updated_at = None
    ev.source_quality = "official"
    ev.classifier_metadata = None
    for k, v in overrides.items():
        setattr(ev, k, v)
    return ev


def _make_incident(**overrides):
    inc = MagicMock()
    inc.id = 1
    inc.incident_category = "crime"
    inc.incident_type = "assault"
    inc.occurred_at = None
    inc.reported_at = None
    inc.city = "Testville"
    inc.province_state = "TX"
    inc.country = "US"
    inc.public_area_label = None
    inc.latitude_public = None
    inc.longitude_public = None
    inc.precision_level = "city"
    inc.source_links = []
    inc.event_links = []
    inc.review_status = "verified"
    inc.reviewed_at = None
    inc.reviewed_by = None
    inc.verification_status = None
    inc.source_url = None
    inc.source_name = None
    inc.data_last_seen_at = None
    for k, v in overrides.items():
        setattr(inc, k, v)
    return inc


def _make_db(return_value):
    db = MagicMock()
    db.scalar.return_value = return_value
    return db


class TestCourtEventTrustFields:
    def test_court_event_source_tier_populated_from_source_quality(self):
        event = _make_event(source_quality="high")
        db = _make_db(event)
        with patch("app.api.routes.map_record.is_public_event", return_value=True):
            result = _court_event_detail("EVT-001", db)
        assert result["source_tier"] == "high"

    def test_court_event_confidence_populated_from_classifier_metadata(self):
        event = _make_event(classifier_metadata={"confidence": 0.85})
        db = _make_db(event)
        with patch("app.api.routes.map_record.is_public_event", return_value=True):
            result = _court_event_detail("EVT-001", db)
        assert result["confidence"] == pytest.approx(0.85)

    def test_court_event_warnings_empty_when_high_confidence(self):
        event = _make_event(classifier_metadata={"confidence": 0.9})
        db = _make_db(event)
        with patch("app.api.routes.map_record.is_public_event", return_value=True):
            result = _court_event_detail("EVT-001", db)
        assert result["warnings"] == []


class TestIncidentTrustFields:
    def test_incident_source_tier_official_when_source_url_present(self):
        incident = _make_incident(source_url="https://police.example.gov/data")
        db = _make_db(incident)
        with patch(
            "app.api.routes.map_record.is_public_crime_incident", return_value=True
        ), patch(
            "app.api.routes.map_record.can_show_public_entity",
            return_value=PublicationDecision(
                allowed=True,
                reasons=[],
                public_status="official_police_open_data_report",
                public_visibility_value=True,
            ),
        ):
            result = _incident_detail("1", db)
        assert result["source_tier"] == "official"

    def test_incident_no_linked_court_record_warning(self):
        incident = _make_incident(source_url=None, verification_status="unverified")
        db = _make_db(incident)
        with patch(
            "app.api.routes.map_record.is_public_crime_incident", return_value=True
        ), patch(
            "app.api.routes.map_record.can_show_public_entity",
            return_value=PublicationDecision(
                allowed=True,
                reasons=[],
                public_status="official_police_open_data_report",
                public_visibility_value=True,
            ),
        ):
            result = _incident_detail("1", db)
        assert "No linked court record" in result["warnings"]

    def test_incident_returns_404_when_publication_policy_denies(self):
        incident = _make_incident()
        db = _make_db(incident)
        with patch(
            "app.api.routes.map_record.is_public_crime_incident", return_value=True
        ), patch(
            "app.api.routes.map_record.can_show_public_entity",
            return_value=PublicationDecision(
                allowed=False,
                reasons=["public_visibility_false"],
                public_status=None,
                public_visibility_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _incident_detail("1", db)
        assert exc_info.value.status_code == 404
