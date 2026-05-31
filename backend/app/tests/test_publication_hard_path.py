from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.entities import (
    Case,
    Court,
    CrimeIncident,
    Event,
    EventSource,
    LegalInstrument,
    LegalSource,
    Location,
    ReviewItem,
    SourceRegistry,
    SourceSnapshot,
)
from app.policies.publication_policy import (
    OFFICIAL_POLICE_OPEN_DATA_REPORT,
    PENDING_REVIEW,
    REMOVED_FROM_PUBLIC,
    VERIFIED_COURT_RECORD,
    can_publish_entity,
    can_show_public_entity,
    set_entity_public_visibility,
)
from app.review.decisions import record_decision


def _suffix() -> str:
    return uuid4().hex


def _snapshot(db_session, *, content_hash: str = "a" * 64) -> SourceSnapshot:
    snap = SourceSnapshot(
        source_key=f"test_{_suffix()}",
        source_url=f"https://example.test/evidence/{_suffix()}",
        fetched_at=datetime.now(timezone.utc),
        content_hash=content_hash,
        raw_content="evidence",
    )
    db_session.add(snap)
    db_session.flush()
    return snap


def _machine_source(db_session) -> SourceRegistry:
    key = f"test_source_{_suffix()}"
    source = SourceRegistry(
        source_key=key,
        source_name="Test machine source",
        source_type="official",
        source_class="machine_ingest",
        lifecycle_state="runnable",
        automation_status="machine_ready_enabled",
        is_active=True,
        public_record_authority="official_legislation",
        base_url="https://laws-lois.justice.gc.ca/",
        allowed_domains='["laws-lois.justice.gc.ca"]',
        parser="justice_laws_xml",
        parser_version="1.0",
        requires_manual_review=True,
        public_publish_default=False,
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_legal_instrument_requires_hashed_raw_snapshot(db_session):
    source = _machine_source(db_session)
    empty_snapshot = _snapshot(db_session, content_hash="")
    instrument = LegalInstrument(
        source_id=source.id,
        jurisdiction="CA",
        instrument_type="act",
        unique_id=f"li-{_suffix()}",
        language="eng",
        title="Test Act",
        raw_snapshot_id=empty_snapshot.id,
        parser_version="1.0",
        review_status=VERIFIED_COURT_RECORD,
        public_visibility="private",
    )
    db_session.add(instrument)
    db_session.flush()

    blocked = can_publish_entity(db_session, "legal_instrument", instrument)
    assert blocked.allowed is False
    assert "missing_raw_snapshot_content_hash" in blocked.reasons

    valid_snapshot = _snapshot(db_session)
    instrument.raw_snapshot_id = valid_snapshot.id
    allowed = can_publish_entity(db_session, "legal_instrument", instrument)
    assert allowed.allowed is True
    set_entity_public_visibility(instrument, True)
    assert can_show_public_entity(db_session, "legal_instrument", instrument).allowed is True

    instrument.review_status = REMOVED_FROM_PUBLIC
    set_entity_public_visibility(instrument, False)
    assert can_show_public_entity(db_session, "legal_instrument", instrument).allowed is False


def test_crime_incident_evidence_and_precision_gate(db_session):
    incident = CrimeIncident(
        incident_type="test incident",
        incident_category="test",
        source_name="test police",
        review_status=OFFICIAL_POLICE_OPEN_DATA_REPORT,
        latitude_public=52.13,
        longitude_public=-106.67,
        precision_level="city_centroid",
    )
    db_session.add(incident)
    db_session.flush()

    no_snapshot = can_publish_entity(db_session, "crime_incident", incident)
    assert no_snapshot.allowed is False
    assert "missing_source_snapshot_id" in no_snapshot.reasons

    incident.source_snapshot_id = _snapshot(db_session, content_hash="").id
    empty_hash = can_publish_entity(db_session, "crime_incident", incident)
    assert empty_hash.allowed is False
    assert "missing_source_snapshot_content_hash" in empty_hash.reasons

    incident.source_snapshot_id = _snapshot(db_session).id
    allowed = can_publish_entity(db_session, "crime_incident", incident)
    assert allowed.allowed is True
    set_entity_public_visibility(incident, True)
    assert can_show_public_entity(db_session, "crime_incident", incident).allowed is True

    incident.precision_level = "exact_private_address"
    assert can_publish_entity(db_session, "crime_incident", incident).allowed is False
    assert can_show_public_entity(db_session, "crime_incident", incident).allowed is False


def test_event_requires_public_legal_source_anchor(db_session):
    court = db_session.query(Court).first()
    case = db_session.query(Case).first()
    location = db_session.query(Location).first()
    event = Event(
        event_id=f"evt-{_suffix()}",
        court_id=court.id,
        case_id=case.id,
        primary_location_id=location.id,
        event_type="decision",
        title="Test reviewed event",
        summary="Reviewed event summary",
        review_status=VERIFIED_COURT_RECORD,
        public_visibility=False,
    )
    db_session.add(event)
    db_session.flush()

    blocked = can_publish_entity(db_session, "event", event)
    assert blocked.allowed is False
    assert "event_missing_public_reviewed_source_link" in blocked.reasons

    legal_source = LegalSource(
        source_id=f"ls-{_suffix()}",
        source_type="court_record",
        title="Court source",
        url=f"https://example.test/source/{_suffix()}",
        url_hash="b" * 64,
        source_quality="court_record",
        verified_flag=True,
        review_status=VERIFIED_COURT_RECORD,
        public_visibility=True,
    )
    db_session.add(legal_source)
    db_session.flush()
    db_session.add(EventSource(event_id=event.id, source_id=legal_source.id))
    db_session.flush()
    db_session.expire(event, ["source_links"])

    assert can_publish_entity(db_session, "event", event).allowed is True
    set_entity_public_visibility(event, True)
    assert can_show_public_entity(db_session, "event", event).allowed is True

    event.review_status = "rejected"
    set_entity_public_visibility(event, False)
    assert can_show_public_entity(db_session, "event", event).allowed is False


def test_review_item_approval_does_not_publish_legal_instrument(db_session):
    source = _machine_source(db_session)
    snap = _snapshot(db_session)
    instrument = LegalInstrument(
        source_id=source.id,
        jurisdiction="CA",
        instrument_type="act",
        unique_id=f"ri-{_suffix()}",
        language="eng",
        title="Draft Act",
        raw_snapshot_id=snap.id,
        parser_version="1.0",
        review_status=PENDING_REVIEW,
        public_visibility="private",
    )
    item = ReviewItem(
        record_type="LegalInstrument",
        source_snapshot_id=snap.id,
        suggested_payload_json={
            "source_key": source.source_key,
            "unique_id": instrument.unique_id,
            "language": instrument.language,
        },
        source_quality="official_legislation",
        confidence=0.95,
        privacy_status="review_required",
        publish_recommendation="manual_review",
        public_visibility=False,
        status="pending",
    )
    db_session.add_all([instrument, item])
    db_session.flush()

    result = record_decision(
        db_session,
        item.id,
        decision="approved",
        reviewer_id="reviewer@example.test",
    )

    assert result.ok is True
    assert item.status == "approved"
    assert item.public_visibility is False
    assert instrument.review_status == PENDING_REVIEW
    assert instrument.public_visibility == "private"
    assert can_show_public_entity(db_session, "legal_instrument", instrument).allowed is False
