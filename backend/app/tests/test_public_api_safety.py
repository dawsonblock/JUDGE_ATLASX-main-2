"""Public API safety checks (Phase 11).

Tests ensuring public endpoints never expose unsafe data.
"""

import hashlib
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.entities import (
    Case,
    Court,
    Defendant,
    Event,
    EventDefendant,
    Judge,
    LegalSource,
    Location,
)
from app.services.constants import PUBLIC_REVIEW_STATUSES


client = TestClient(app)


def _make_url_hash(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("url_hash requires a non-empty URL")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@pytest.fixture
def db_session():
    """Create a test database session."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def setup_test_data(db_session: Session):
    """Create test data for safety checks."""
    public_status = "verified_court_record"
    suffix = uuid4().hex[:8]
    source_id = f"TEST-SOURCE-{suffix}"
    private_source_id = f"TEST-SOURCE-PRIVATE-{suffix}"
    public_event_id = f"EVT-PUBLIC-{suffix}"
    private_event_id = f"EVT-PRIVATE-{suffix}"
    pending_event_id = f"EVT-PENDING-{suffix}"

    # Create location
    location = Location(
        name="Toronto Courthouse",
        location_type="courthouse",
        city="Toronto",
        state="ON",
        region="CA-ON",
        latitude=43.6532,
        longitude=-79.3832,
    )
    db_session.add(location)
    db_session.flush()

    # Create court
    court = Court(
        courtlistener_id=f"test-court-ca-on-{uuid4().hex[:8]}",
        name="Test Court",
        jurisdiction="CA-ON",
        location_id=location.id,
    )
    db_session.add(court)
    db_session.flush()

    # Create judge
    judge = Judge(
        name="Test Judge",
        normalized_name=f"test-judge-{uuid4().hex[:8]}",
        court_id=court.id,
        cl_person_id=f"TEST-JUDGE-{uuid4().hex[:8]}",
    )
    db_session.add(judge)
    db_session.flush()

    # Create case
    case = Case(
        docket_number="TEST-2024-001",
        normalized_docket_number="test-2024-001",
        caption="Test v. Example",
        case_type="criminal",
        filed_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        court_id=court.id,
    )
    db_session.add(case)
    db_session.flush()

    # Create defendant
    defendant = Defendant(
        anonymized_id=f"DEF-{uuid4().hex[:8]}",
    )
    db_session.add(defendant)
    db_session.flush()

    # Create legal source
    source_url = f"https://example.test/source/{source_id.lower()}"
    source = LegalSource(
        source_id=source_id,
        title="Test Source",
        source_type="court_record",
        url=source_url,
        url_hash=_make_url_hash(source_url),
        source_quality="official",
        public_visibility=True,
        review_status=public_status,
    )
    db_session.add(source)
    db_session.flush()

    # Create public event (should be visible)
    public_event = Event(
        event_id=public_event_id,
        case_id=case.id,
        court_id=court.id,
        judge_id=judge.id,
        primary_location_id=location.id,
        event_type="published_opinion",
        title="Public hearing",
        summary="Public hearing summary",
        decision_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        public_visibility=True,
        review_status=public_status,
    )
    db_session.add(public_event)
    db_session.flush()

    # Link defendant to public event
    event_defendant = EventDefendant(
        event_id=public_event.id,
        defendant_id=defendant.id,
    )
    db_session.add(event_defendant)
    db_session.flush()

    # Create private event (should NOT be visible)
    private_event = Event(
        event_id=private_event_id,
        case_id=case.id,
        court_id=court.id,
        judge_id=judge.id,
        primary_location_id=location.id,
        event_type="published_opinion",
        title="Private hearing",
        summary="Private hearing summary",
        decision_date=datetime(2024, 1, 20, tzinfo=timezone.utc),
        public_visibility=False,
        review_status=public_status,
    )
    db_session.add(private_event)
    db_session.flush()

    # Create pending review event (should NOT be visible)
    pending_event = Event(
        event_id=pending_event_id,
        case_id=case.id,
        court_id=court.id,
        judge_id=judge.id,
        primary_location_id=location.id,
        event_type="published_opinion",
        title="Pending hearing",
        summary="Pending hearing summary",
        decision_date=datetime(2024, 1, 25, tzinfo=timezone.utc),
        public_visibility=True,
        review_status="pending_review",
    )
    db_session.add(pending_event)
    db_session.flush()

    # Create private source (should NOT be visible)
    private_source_url = f"https://example.test/source/{private_source_id.lower()}"
    private_source = LegalSource(
        source_id=private_source_id,
        title="Private Source",
        source_type="court_record",
        url=private_source_url,
        url_hash=_make_url_hash(private_source_url),
        source_quality="official",
        public_visibility=False,
        review_status=public_status,
    )
    db_session.add(private_source)
    db_session.flush()

    db_session.commit()

    return {
        "court": court,
        "location": location,
        "judge": judge,
        "case": case,
        "defendant": defendant,
        "source": source,
        "public_event": public_event,
        "private_event": private_event,
        "pending_event": pending_event,
        "private_source": private_source,
    }


def test_list_events_excludes_private_events(setup_test_data):
    """Public /api/events endpoint must not expose events with public_visibility=False."""
    response = client.get("/api/events")
    assert response.status_code == 200
    
    events = response.json()
    event_ids = [e["event_id"] for e in events]
    
    # Private event should NOT be visible
    assert setup_test_data["private_event"].event_id not in event_ids
    
    # Pending review event should NOT be visible
    assert setup_test_data["pending_event"].event_id not in event_ids


def test_get_event_returns_404_for_private_event(setup_test_data):
    """Public /api/events/{event_id} endpoint must return 404 for private events."""
    response = client.get(f"/api/events/{setup_test_data['private_event'].event_id}")
    assert response.status_code == 404


def test_get_event_returns_404_for_pending_review_event(setup_test_data):
    """Public /api/events/{event_id} endpoint must return 404 for pending review events."""
    response = client.get(f"/api/events/{setup_test_data['pending_event'].event_id}")
    assert response.status_code == 404


def test_list_judges_excludes_judges_without_public_events(setup_test_data, db_session: Session):
    """Public /api/judges endpoint must not expose judges without public events."""
    # Add a judge with no public events
    court = setup_test_data["court"]
    private_judge = Judge(
        name="Private Judge",
        normalized_name=f"private-judge-{uuid4().hex[:8]}",
        court_id=court.id,
        cl_person_id=f"PRIVATE-JUDGE-{uuid4().hex[:8]}",
    )
    db_session.add(private_judge)
    db_session.commit()
    
    response = client.get("/api/judges")
    assert response.status_code == 200
    
    judges = response.json()
    judge_names = [j["name"] for j in judges]
    
    # Private judge (without public events) should NOT be visible
    assert "Private Judge" not in judge_names


def test_get_judge_returns_404_for_judge_without_public_events(setup_test_data, db_session: Session):
    """Public /api/judges/{judge_id} endpoint must return 404 for judges without public events."""
    court = setup_test_data["court"]
    private_judge = Judge(
        name="Private Judge",
        normalized_name=f"private-judge-two-{uuid4().hex[:8]}",
        court_id=court.id,
        cl_person_id=f"PRIVATE-JUDGE-TWO-{uuid4().hex[:8]}",
    )
    db_session.add(private_judge)
    db_session.commit()
    
    response = client.get(f"/api/judges/{private_judge.id}")
    assert response.status_code == 404


def test_list_cases_excludes_cases_without_public_events(setup_test_data, db_session: Session):
    """Public /api/cases endpoint must not expose cases without public events."""
    # Add a case with no public events
    court = setup_test_data["court"]
    private_case = Case(
        docket_number="PRIVATE-2024-001",
        normalized_docket_number="private-2024-001",
        caption="Private v. Example",
        case_type="criminal",
        filed_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        court_id=court.id,
    )
    db_session.add(private_case)
    db_session.commit()
    
    response = client.get("/api/cases")
    assert response.status_code == 200
    
    cases = response.json()
    case_numbers = [c["docket_number"] for c in cases]
    
    # Private case (without public events) should NOT be visible
    assert "PRIVATE-2024-001" not in case_numbers


def test_get_case_returns_404_for_case_without_public_events(setup_test_data, db_session: Session):
    """Public /api/cases/{case_id} endpoint must return 404 for cases without public events."""
    court = setup_test_data["court"]
    private_case = Case(
        docket_number="PRIVATE-2024-001",
        normalized_docket_number="private-2024-001-b",
        caption="Private v. Example B",
        case_type="criminal",
        filed_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        court_id=court.id,
    )
    db_session.add(private_case)
    db_session.commit()
    
    response = client.get(f"/api/cases/{private_case.id}")
    assert response.status_code == 404


def test_list_sources_excludes_private_sources(setup_test_data):
    """Public /api/sources endpoint must not expose sources with public_visibility=False."""
    response = client.get("/api/sources")
    assert response.status_code == 200
    
    sources = response.json()
    source_ids = [s["source_id"] for s in sources]
    
    # Private source should NOT be visible
    assert setup_test_data["private_source"].source_id not in source_ids


def test_get_source_returns_404_for_private_source(setup_test_data):
    """Public /api/sources/{source_id} endpoint must return 404 for private sources."""
    response = client.get(f"/api/sources/{setup_test_data['private_source'].source_id}")
    assert response.status_code == 404


def test_get_defendant_anonymizes_personal_data(setup_test_data):
    """Public /api/defendants/{defendant_id} endpoint must not expose personal data."""
    defendant_id = setup_test_data["defendant"].id
    response = client.get(f"/api/defendants/{defendant_id}")
    assert response.status_code == 200
    
    data = response.json()
    
    # Should only return anonymized data
    assert "id" in data
    assert "anonymized_id" in data
    assert "display_label" in data
    assert data["display_label"] == data["anonymized_id"]
    
    # Should include warning about no personal location tracking
    assert "warning" in data
    assert "No personal location tracking" in data["warning"]


def test_get_defendant_returns_404_for_defendant_without_public_events(setup_test_data, db_session: Session):
    """Public /api/defendants/{defendant_id} endpoint must return 404 for defendants without public events."""
    # Add a defendant with no public events
    private_defendant = Defendant(
        anonymized_id=f"DEF-PRIVATE-{uuid4().hex[:8]}",
    )
    db_session.add(private_defendant)
    db_session.commit()
    
    response = client.get(f"/api/defendants/{private_defendant.id}")
    assert response.status_code == 404


def test_defendant_timeline_excludes_private_events(setup_test_data):
    """Public /api/defendants/{defendant_id}/timeline endpoint must not expose private events."""
    defendant_id = setup_test_data["defendant"].id
    response = client.get(f"/api/defendants/{defendant_id}/timeline")
    assert response.status_code == 200
    
    events = response.json()
    event_ids = [e["event_id"] for e in events]
    
    # Private event should NOT be visible
    assert setup_test_data["private_event"].event_id not in event_ids
    
    # Pending review event should NOT be visible
    assert setup_test_data["pending_event"].event_id not in event_ids


def test_case_timeline_excludes_private_events(setup_test_data):
    """Public /api/cases/{case_id}/timeline endpoint must not expose private events."""
    case_id = setup_test_data["case"].id
    response = client.get(f"/api/cases/{case_id}/timeline")
    assert response.status_code == 200
    
    events = response.json()
    event_ids = [e["event_id"] for e in events]
    
    # Private event should NOT be visible
    assert setup_test_data["private_event"].event_id not in event_ids
    
    # Pending review event should NOT be visible
    assert setup_test_data["pending_event"].event_id not in event_ids


def test_judge_events_excludes_private_events(setup_test_data):
    """Public /api/judges/{judge_id}/events endpoint must not expose private events."""
    judge_id = setup_test_data["judge"].id
    response = client.get(f"/api/judges/{judge_id}/events")
    assert response.status_code == 200
    
    events = response.json()
    event_ids = [e["event_id"] for e in events]
    
    # Private event should NOT be visible
    assert setup_test_data["private_event"].event_id not in event_ids
    
    # Pending review event should NOT be visible
    assert setup_test_data["pending_event"].event_id not in event_ids


def test_all_non_public_review_statuses_are_filtered(setup_test_data, db_session: Session):
    """Public endpoints must filter all non-public review statuses."""
    case = setup_test_data["case"]
    court = setup_test_data["court"]
    judge = setup_test_data["judge"]
    location = setup_test_data["location"]
    
    # Create events with each non-public review status
    non_public_statuses = ["pending", "rejected", "needs_info", "draft"]
    
    for idx, status in enumerate(non_public_statuses):
        event = Event(
            event_id=f"EVT-{status.upper()}-001",
            case_id=case.id,
            court_id=court.id,
            judge_id=judge.id,
            primary_location_id=location.id,
            event_type="published_opinion",
            title=f"{status} hearing",
            summary=f"{status} hearing summary",
            decision_date=datetime(2024, idx + 2, 1, tzinfo=timezone.utc),
            public_visibility=True,
            review_status=status,
        )
        db_session.add(event)
    
    db_session.commit()
    
    response = client.get("/api/events")
    assert response.status_code == 200
    
    events = response.json()
    event_ids = [e["event_id"] for e in events]
    
    # All non-public status events should NOT be visible
    for status in non_public_statuses:
        assert f"EVT-{status.upper()}-001" not in event_ids
    
    # Safety assertion scope: only verify non-public states never leak.


def test_public_endpoints_never_expose_internal_fields(setup_test_data):
    """Public endpoints must never expose internal database fields."""
    listing = client.get("/api/events")
    assert listing.status_code == 200
    events = listing.json()
    assert events

    response = client.get(f"/api/events/{events[0]['event_id']}")
    assert response.status_code == 200
    
    event = response.json()
    
    # Check that internal fields are not exposed
    assert "id" not in event  # Internal database ID
    assert "internal_notes" not in event
    assert "audit_log" not in event
    
    # Only public-safe fields should be present
    assert "event_id" in event
    assert "event_type" in event
    assert "decision_date" in event
