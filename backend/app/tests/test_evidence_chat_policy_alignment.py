from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.entities import (
    CrimeIncident,
    CrimeIncidentEventLink,
    Event,
    LegalInstrument,
    LegalSection,
    RelationshipEvidence,
    SourceRegistry,
    SourceSnapshot,
)
from app.services.evidence_chat import chat_about_evidence


def _snapshot(db_session, *, content_hash: str = "a" * 64):
    snapshot = SourceSnapshot(
        source_key="justice_canada_laws_xml",
        source_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
        fetched_at=datetime.now(timezone.utc),
        content_hash=content_hash,
        raw_content="fixture",
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def _source(db_session) -> SourceRegistry:
    existing = (
        db_session.query(SourceRegistry)
        .filter(SourceRegistry.source_key == "justice_canada_laws_xml")
        .first()
    )
    if existing is not None:
        return existing

    source = SourceRegistry(
        source_key="justice_canada_laws_xml",
        source_name="Justice Canada Laws XML",
        source_type="official",
        source_class="machine_ingest",
        lifecycle_state="runnable",
        automation_status="machine_ready_enabled",
        is_active=True,
        public_record_authority="official_legislation",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains='["laws-lois.justice.gc.ca"]',
        parser="laws_justice_xml",
        parser_version="justice_laws_xml_v1",
        requires_manual_review=True,
        public_publish_default=False,
        creates='["SourceSnapshot", "LegalInstrument", "LegalSection", "ReviewItem"]',
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_evidence_chat_does_not_cite_pending_legal_instrument(db_session):
    source = _source(db_session)
    snap = _snapshot(db_session)
    instrument = LegalInstrument(
        source_id=source.id,
        jurisdiction="CA-FED",
        instrument_type="act",
        unique_id=f"CHAT-PENDING-{uuid4().hex[:8]}",
        language="eng",
        title="Criminal Code",
        raw_snapshot_id=snap.id,
        parser_version="justice_laws_xml_v1",
        review_status="pending_review",
        public_visibility="private",
    )
    db_session.add(instrument)
    db_session.flush()
    db_session.add(
        LegalSection(
            legal_instrument_id=instrument.id,
            section_label="1",
            text="Test legal section",
            raw_snapshot_id=snap.id,
        )
    )
    db_session.commit()

    result = chat_about_evidence(db_session, "criminal code section")
    assert result.legal_context_citations == []


def test_evidence_chat_does_not_cite_legal_instrument_with_missing_hash(db_session):
    source = _source(db_session)
    snap = _snapshot(db_session, content_hash="")
    instrument = LegalInstrument(
        source_id=source.id,
        jurisdiction="CA-FED",
        instrument_type="act",
        unique_id=f"CHAT-MISSING-HASH-{uuid4().hex[:8]}",
        language="eng",
        title="Another Act",
        raw_snapshot_id=snap.id,
        parser_version="justice_laws_xml_v1",
        review_status="verified_court_record",
        public_visibility="public",
    )
    db_session.add(instrument)
    db_session.flush()
    db_session.add(
        LegalSection(
            legal_instrument_id=instrument.id,
            section_label="2",
            text="Another legal section",
            raw_snapshot_id=snap.id,
        )
    )
    db_session.commit()

    result = chat_about_evidence(db_session, "another act section")
    assert result.legal_context_citations == []


def test_evidence_chat_respects_relationship_policy_gate(db_session):
    incident = CrimeIncident(
        source_name="test_source",
        incident_type="theft",
        incident_category="property",
        review_status="verified_court_record",
        is_public=True,
    )
    db_session.add(incident)
    db_session.flush()

    evidence = RelationshipEvidence(
        from_entity_type="crime_incident",
        from_entity_id=incident.id,
        to_entity_type="person",
        to_entity_id=999,
        relationship_type="linked",
        evidence_type="report",
        evidence_source="fixture",
        extracted_by="test",
        confidence=0.9,
        public_visibility=True,
        review_status="verified_court_record",
        verification_status="rejected",
        relationship_status="active",
    )
    db_session.add(evidence)
    db_session.commit()

    result = chat_about_evidence(db_session, "what evidence exists", incident_id=incident.id)
    assert result.citations == []


def test_evidence_chat_does_not_cite_event_when_event_not_public(db_session):
    event = Event(
        event_id="evt-chat-policy",
        court_id=1,
        case_id=1,
        primary_location_id=1,
        event_type="hearing",
        title="Pending Event",
        summary="Not public",
        review_status="pending_review",
        public_visibility=False,
    )
    db_session.add(event)
    db_session.flush()

    incident = CrimeIncident(
        source_name="test_source",
        incident_type="assault",
        incident_category="violent",
        review_status="verified_court_record",
        is_public=True,
    )
    db_session.add(incident)
    db_session.flush()
    db_session.add(
        CrimeIncidentEventLink(
            crime_incident_id=incident.id,
            event_id=event.id,
            relationship_status="verified_source_link",
        )
    )
    db_session.add(
        RelationshipEvidence(
            from_entity_type="event",
            from_entity_id=event.id,
            to_entity_type="crime_incident",
            to_entity_id=incident.id,
            relationship_type="linked",
            evidence_type="report",
            evidence_source="fixture",
            extracted_by="test",
            confidence=0.9,
            public_visibility=True,
            review_status="verified_court_record",
            verification_status="verified",
            relationship_status="active",
        )
    )
    db_session.commit()

    result = chat_about_evidence(db_session, "what evidence exists", incident_id=incident.id)
    assert result.citations == []
