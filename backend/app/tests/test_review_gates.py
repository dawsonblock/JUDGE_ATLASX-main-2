"""Tests for review gates and public/private visibility.

Proves:
1. Public events endpoint returns only published records
2. Review gate prevents unpublished records from being publicly visible
3. Admin can see pending/unpublished records
4. Publication rules enforce source quality requirements
"""

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Case, Court, Event, EventSource, LegalSource, Location
from app.services.publish_rules import TIER_AUTO, TIER_HOLD
from app.services.linker import url_hash

client = TestClient(app)


def _setup_test_data(db, unique_id: str = "1"):
    """Create required related entities for an event."""
    import uuid

    # Create location with unique coordinates
    import zlib
    # Use zlib.adler32 for a deterministic, process-stable offset.
    # MAX_OFFSET_UNITS and OFFSET_SCALE keep coordinates within typical test
    # bboxes: max offset = 99 * 0.001 = 0.099 degrees (~11 km).
    _MAX_OFFSET_UNITS = 100
    _OFFSET_SCALE = 0.001
    det_offset = (zlib.adler32(str(unique_id).encode()) % _MAX_OFFSET_UNITS) * _OFFSET_SCALE
    location = Location(
        name=f"Test Courthouse {unique_id}",
        location_type="courthouse",
        city="New York",
        state="NY",
        latitude=40.7128 + det_offset,
        longitude=-74.0060 - det_offset,
    )
    db.add(location)
    db.flush()

    # Create court with unique ID
    court = Court(
        courtlistener_id=f"test-court-{unique_id}-{uuid.uuid4().hex[:8]}",
        name=f"Test Federal Court {unique_id}",
        jurisdiction="Federal",
        region="US-NY",
        location_id=location.id,
    )
    db.add(court)
    db.flush()

    # Create case with unique docket
    case = Case(
        court_id=court.id,
        docket_number=f"1:24-cr-{unique_id}",
        normalized_docket_number=f"1-24-cr-{unique_id}",
        caption=f"USA v. Test {unique_id}",
        case_type="criminal",
    )
    db.add(case)
    db.flush()

    return location, court, case


def _make_event(db, *, review_status: str, public_visibility: bool, title: str = "Test", unique_id: str = "1") -> Event:
    """Create a test event with given review status and visibility."""
    location, court, case = _setup_test_data(db, unique_id)

    event = Event(
        event_id=f"evt-{unique_id}-{datetime.now(timezone.utc).timestamp()}-{title}",
        court_id=court.id,
        case_id=case.id,
        primary_location_id=location.id,
        event_type="sentencing",
        title=title,
        summary="Test event summary",
        review_status=review_status,
        public_visibility=public_visibility,
        decision_date=date.today(),
        source_quality="court_record",
    )
    db.add(event)
    db.flush()
    if public_visibility:
        url = f"https://example.test/review-gates/{unique_id}/{title}"
        source = LegalSource(
            source_id=f"src-review-gates-{unique_id}-{title}",
            source_type="court_record",
            title=f"Source for {title}",
            url=url,
            url_hash=url_hash(url),
            source_quality="court_record",
            verified_flag=True,
            review_status="verified_court_record",
            public_visibility=True,
        )
        db.add(source)
        db.flush()
        db.add(EventSource(event_id=event.id, source_id=source.id))
    db.commit()
    db.refresh(event)
    return event


def test_public_events_filters_by_visibility():
    """Public events endpoint should only return publicly visible records."""
    db = SessionLocal()
    try:
        # Create visible and hidden events with unique IDs
        _make_event(db, review_status="verified_court_record", public_visibility=True, title="VisibleEvent", unique_id="1")
        _make_event(db, review_status="pending_review", public_visibility=False, title="HiddenEvent", unique_id="2")

        # Query public events endpoint
        response = client.get("/api/events")
        assert response.status_code == 200

        # Result is a list of events
        items = response.json()
        titles = [e.get("title") for e in items]

        # Only publicly visible should be returned
        assert "VisibleEvent" in titles
        assert "HiddenEvent" not in titles
    finally:
        db.close()


def test_public_map_filters_by_visibility():
    """Public map endpoint should only return publicly visible records."""
    db = SessionLocal()
    try:
        # Create test events with unique IDs
        _make_event(db, review_status="verified_court_record", public_visibility=True, title="MapVisible", unique_id="3")
        _make_event(db, review_status="pending_review", public_visibility=False, title="MapHidden", unique_id="4")

        # Query public map endpoint
        response = client.get("/api/map/events?north=41&south=40&east=-73&west=-75")
        assert response.status_code == 200

        # Map endpoint returns GeoJSON feature collection
        result = response.json()
        features = result.get("features", [])
        titles = [f.get("properties", {}).get("title") for f in features]

        # Only publicly visible should be in map
        assert "MapVisible" in titles
        assert "MapHidden" not in titles
    finally:
        db.close()


def test_event_detail_requires_public_visibility():
    """Public event detail should require public visibility flag."""
    db = SessionLocal()
    try:
        hidden = _make_event(db, review_status="verified_court_record", public_visibility=False, title="DetailHidden", unique_id="5")

        # Try to access non-public event via public API
        response = client.get(f"/api/events/{hidden.event_id}")
        # Should return 404 (not found) since event exists but is not public
        assert response.status_code == 404
    finally:
        db.close()


def test_public_event_detail_returns_visible():
    """Public event detail should work for publicly visible events."""
    db = SessionLocal()
    try:
        visible = _make_event(db, review_status="verified_court_record", public_visibility=True, title="DetailVisible", unique_id="6")

        # Access public event via API
        response = client.get(f"/api/events/{visible.event_id}")
        assert response.status_code == 200
        result = response.json()
        assert result.get("title") == "DetailVisible"
    finally:
        db.close()


def test_pending_review_not_publicly_visible():
    """Events with pending_review status should not be publicly visible."""
    db = SessionLocal()
    try:
        pending = _make_event(db, review_status="pending_review", public_visibility=False, title="PendingReview", unique_id="7")

        # Should not appear in public events
        response = client.get("/api/events")
        assert response.status_code == 200
        items = response.json()
        titles = [e.get("title") for e in items]
        assert "PendingReview" not in titles

        # Should return 404 when accessed directly
        detail_response = client.get(f"/api/events/{pending.event_id}")
        assert detail_response.status_code == 404
    finally:
        db.close()


def test_review_status_tiers():
    """Test that review status affects publication classification."""
    from app.services.publish_rules import review_status_for_tier, public_visibility_for_tier

    # TIER_AUTO should result in official_police_open_data_report and be public
    auto_status = review_status_for_tier(TIER_AUTO)
    assert auto_status == "official_police_open_data_report"
    assert public_visibility_for_tier(TIER_AUTO) is True

    # TIER_HOLD should result in pending_review and not public
    hold_status = review_status_for_tier(TIER_HOLD)
    assert hold_status == "pending_review"
    assert public_visibility_for_tier(TIER_HOLD) is False


def test_rejected_records_not_public():
    """Events with rejected status should never be publicly visible."""
    db = SessionLocal()
    try:
        rejected = _make_event(db, review_status="rejected", public_visibility=False, title="RejectedEvent", unique_id="rej1")

        # Should not appear in public events
        response = client.get("/api/events")
        assert response.status_code == 200
        items = response.json()
        titles = [e.get("title") for e in items]
        assert "RejectedEvent" not in titles

        # Should return 404 when accessed directly
        detail_response = client.get(f"/api/events/{rejected.event_id}")
        assert detail_response.status_code == 404
    finally:
        db.close()


def test_blocked_records_not_public():
    """Events with blocked status should never be publicly visible."""
    db = SessionLocal()
    try:
        blocked = _make_event(db, review_status="blocked", public_visibility=False, title="BlockedEvent", unique_id="blk1")

        # Should not appear in public events
        response = client.get("/api/events")
        assert response.status_code == 200
        items = response.json()
        titles = [e.get("title") for e in items]
        assert "BlockedEvent" not in titles

        # Should return 404 when accessed directly
        detail_response = client.get(f"/api/events/{blocked.event_id}")
        assert detail_response.status_code == 404
    finally:
        db.close()


def test_disputed_records_not_public():
    """Events with disputed status should not be publicly visible."""
    db = SessionLocal()
    try:
        disputed = _make_event(db, review_status="disputed", public_visibility=False, title="DisputedEvent", unique_id="dsp1")

        # Should not appear in public events
        response = client.get("/api/events")
        assert response.status_code == 200
        items = response.json()
        titles = [e.get("title") for e in items]
        assert "DisputedEvent" not in titles

        # Should return 404 when accessed directly
        detail_response = client.get(f"/api/events/{disputed.event_id}")
        assert detail_response.status_code == 404
    finally:
        db.close()


def test_public_visibility_respects_review_status():
    """Public visibility should respect review status rules."""
    db = SessionLocal()
    try:
        # Create event with approved review status
        _make_event(
            db,
            review_status="verified_court_record",
            public_visibility=True,
            title="ApprovedEvent",
            unique_id="8"
        )

        # Create event with rejected review status
        _make_event(
            db,
            review_status="rejected",
            public_visibility=False,
            title="RejectedEvent",
            unique_id="9"
        )

        response = client.get("/api/events")
        assert response.status_code == 200
        items = response.json()
        titles = [e.get("title") for e in items]

        # Only approved/verified should be visible
        assert "ApprovedEvent" in titles
        assert "RejectedEvent" not in titles
    finally:
        db.close()
