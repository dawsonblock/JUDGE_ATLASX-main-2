"""Materializer for converting evidence-backed data into GeoLegalEvent format.

This module converts various data models (Event, CrimeIncident, MemoryClaim, LegalInstrument)
into the normalized GeoLegalEvent format for map rendering. It applies business logic for
confidence scoring, review status, and publication gates.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.confidence_engine import calculate_claim_confidence
from app.memory.contradiction_engine import get_open_contradictions_by_claim
from app.models.entities import (
    CanonicalEntity,
    CrimeIncident,
    Event,
    LegalInstrument,
    MemoryEvidenceLink,
    MemoryClaim,
    SourceSnapshot,
)
from app.review.publication_gate import (
    assert_legal_instrument_publication_ready,
    assert_memory_claim_publication_ready,
)
from app.policies.public_status import (
    PUBLIC_ADMIN_ONLY,
    PUBLIC_PRIVATE,
    PUBLIC_REDACTED,
    PUBLIC_SAFE,
    REVIEW_APPROVED,
    REVIEW_PENDING,
)
from app.schemas.geo_legal_event import (
    EVENT_TYPES,
    GeoLegalEvent,
    PUBLISH_STATUSES,
    REVIEW_STATUSES,
    get_confidence_label,
)

logger = logging.getLogger(__name__)

# Pagination configuration
DEFAULT_QUERY_LIMIT = 1000
MAX_QUERY_LIMIT = 10000

def materialize_from_event(event: Event, db: Session) -> GeoLegalEvent | None:
    """Convert a court Event to GeoLegalEvent format.

    Args:
        event: The Event to convert
        db: Database session

    Returns:
        GeoLegalEvent or None if conversion fails
    """
    try:
        # Get location from event's primary location
        if not event.primary_location:
            logger.warning(f"Event {event.id} has no primary location")
            return None

        location = event.primary_location
        if not location.latitude or not location.longitude:
            logger.warning(f"Event {event.id} location has no coordinates")
            return None

        # Get source information
        source_ids = []
        if event.sources:
            for source_link in event.sources:
                source_ids.append(str(source_link.source_id))

        # Get evidence IDs (event sources act as evidence)
        evidence_ids = source_ids.copy()

        # Calculate confidence based on source quality and verification
        confidence = 0.8 if event.verified_flag else 0.6
        if event.source_quality == "court_record":
            confidence = 0.9
        elif event.source_quality == "government_data":
            confidence = 0.85

        # Determine review status
        review_status = event.review_status or REVIEW_PENDING
        if event.verified_flag and review_status == REVIEW_PENDING:
            review_status = REVIEW_APPROVED

        # Determine publish status
        publish_status = PUBLIC_SAFE
        if not event.verified_flag:
            publish_status = PUBLIC_ADMIN_ONLY
        if review_status != REVIEW_APPROVED:
            publish_status = PUBLIC_PRIVATE

        # Build tags
        tags = ["court_event"]
        if event.repeat_offender_indicator:
            tags.append("repeat_offender")
        if event.event_type:
            tags.append(event.event_type)

        return GeoLegalEvent(
            id=f"event:{event.id}",
            event_type="court_event",
            title=event.title or f"Court Event {event.event_id}",
            description=event.summary,
            lat=location.latitude,
            lng=location.longitude,
            location_name=location.name,
            occurred_at=event.decision_date,
            published_at=event.posted_date,
            jurisdiction=event.court.jurisdiction if event.court else "unknown",
            province=event.court.region if event.court else None,
            country="Canada",
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            claim_ids=[],
            confidence=confidence,
            confidence_label=get_confidence_label(confidence),
            review_status=review_status,
            publish_status=publish_status,
            tags=tags,
            metadata={
                "event_id": event.event_id,
                "court_id": event.court_id,
                "judge_id": event.judge_id,
                "case_id": event.case_id,
                "event_type": event.event_type,
                "verified_flag": event.verified_flag,
                "source_quality": event.source_quality,
            },
        )
    except Exception as e:
        logger.error(f"Failed to materialize event {event.id}: {e}", exc_info=True)
        return None


def materialize_from_crime_incident(
    incident: CrimeIncident, db: Session
) -> GeoLegalEvent | None:
    """Convert a CrimeIncident to GeoLegalEvent format.

    Args:
        incident: The CrimeIncident to convert
        db: Database session

    Returns:
        GeoLegalEvent or None if conversion fails
    """
    try:
        # Check if incident has public coordinates
        if not incident.latitude_public or not incident.longitude_public:
            logger.warning(f"CrimeIncident {incident.id} has no public coordinates")
            return None

        # Get source information
        source_ids = []
        if incident.source_links:
            for source_link in incident.source_links:
                source_ids.append(str(source_link.source_id))

        # Get evidence IDs (incident sources act as evidence)
        evidence_ids = source_ids.copy()

        # Calculate confidence based on verification status
        confidence = 0.5
        if incident.verification_status == "verified":
            confidence = 0.8
        elif incident.verification_status == "partially_verified":
            confidence = 0.6

        # Determine review status
        review_status = incident.review_status or REVIEW_PENDING

        # Determine publish status
        publish_status = PUBLIC_SAFE
        if not incident.is_public:
            publish_status = PUBLIC_PRIVATE
        if review_status != REVIEW_APPROVED:
            publish_status = PUBLIC_ADMIN_ONLY
        if incident.precision_level in ["exact_address", "street_level"]:
            publish_status = PUBLIC_ADMIN_ONLY

        # Build tags
        tags = ["crime_event"]
        if incident.incident_category:
            tags.append(incident.incident_category)
        if incident.is_aggregate:
            tags.append("aggregate")

        return GeoLegalEvent(
            id=f"crime:{incident.id}",
            event_type="crime_event",
            title=incident.incident_category or "Crime Incident",
            description=incident.summary,
            lat=incident.latitude_public,
            lng=incident.longitude_public,
            location_name=incident.city,
            occurred_at=incident.reported_at,
            published_at=incident.reported_at,
            jurisdiction=incident.jurisdiction or "unknown",
            province=incident.province_state,
            country=incident.country or "Canada",
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            claim_ids=[],
            confidence=confidence,
            confidence_label=get_confidence_label(confidence),
            review_status=review_status,
            publish_status=publish_status,
            tags=tags,
            metadata={
                "incident_id": incident.id,
                "verification_status": incident.verification_status,
                "is_aggregate": incident.is_aggregate,
                "precision_level": incident.precision_level,
                "source_name": incident.source_name,
            },
        )
    except Exception as e:
        logger.error(f"Failed to materialize incident {incident.id}: {e}", exc_info=True)
        return None


def materialize_from_memory_claim(
    claim: MemoryClaim, db: Session
) -> GeoLegalEvent | None:
    """Convert a MemoryClaim to GeoLegalEvent format.

    Only materializes claims that pass the publication gate.

    Args:
        claim: The MemoryClaim to convert
        db: Database session

    Returns:
        GeoLegalEvent or None if claim fails publication gate
    """
    try:
        # Check publication gate
        try:
            assert_memory_claim_publication_ready(claim, db)
        except Exception as e:
            logger.debug(f"Claim {claim.id} failed publication gate: {e}")
            return None

        # Get location from entity
        entity = db.query(CanonicalEntity).filter(
            CanonicalEntity.id == claim.entity_id
        ).first()
        if not entity or not entity.latitude or not entity.longitude:
            logger.warning(f"Claim {claim.id} entity has no coordinates")
            return None

        # Get source information
        source_ids = []
        evidence_ids = []
        if claim.source_snapshot_id:
            snapshot = db.query(SourceSnapshot).filter(
                SourceSnapshot.id == claim.source_snapshot_id
            ).first()
            if snapshot:
                source_ids.append(str(snapshot.source_id))
                evidence_ids.append(str(snapshot.id))

        # Get evidence links
        evidence_links = db.query(MemoryEvidenceLink).filter(
            MemoryEvidenceLink.claim_id == claim.id
        ).all()
        for link in evidence_links:
            if link.evidence_snapshot_id:
                evidence_ids.append(str(link.evidence_snapshot_id))

        # Check for contradictions
        open_contradictions = get_open_contradictions_by_claim(claim.id, db)
        has_contradiction = open_contradictions is not None and len(open_contradictions) > 0

        # Determine publish status
        publish_status = PUBLIC_SAFE
        if has_contradiction:
            publish_status = PUBLIC_ADMIN_ONLY
        if claim.claim_sensitivity in [
            "criminal_allegation_named_person",
            "criminal_allegation_private_person",
        ]:
            publish_status = PUBLIC_REDACTED

        # Build tags
        tags = [claim.claim_type]
        if claim.predicate:
            tags.append(claim.predicate)
        if has_contradiction:
            tags.append("contradicted")

        return GeoLegalEvent(
            id=f"claim:{claim.id}",
            event_type="contradiction_event" if has_contradiction else "news_event",
            title=claim.claim_value[:200] if claim.claim_value and len(claim.claim_value) > 200 else (claim.claim_value or "Claim"),
            description=claim.normalized_value,
            lat=entity.latitude,
            lng=entity.longitude,
            location_name=entity.name,
            occurred_at=claim.observed_at,
            published_at=claim.created_at,
            jurisdiction=claim.jurisdiction or "unknown",
            province=None,
            country="Canada",
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            claim_ids=[str(claim.id)],
            confidence=claim.confidence,
            confidence_label=get_confidence_label(claim.confidence),
            review_status=claim.review_status,
            publish_status=publish_status,
            tags=tags,
            metadata={
                "claim_id": claim.id,
                "claim_type": claim.claim_type,
                "predicate": claim.predicate,
                "claim_sensitivity": claim.claim_sensitivity,
                "has_contradiction": has_contradiction,
                "contradiction_count": len(open_contradictions),
            },
        )
    except Exception as e:
        logger.error(f"Failed to materialize claim {claim.id}: {e}", exc_info=True)
        return None


def materialize_from_legal_instrument(
    instrument: LegalInstrument, db: Session
) -> GeoLegalEvent | None:
    """Convert a LegalInstrument to GeoLegalEvent format.

    Args:
        instrument: The LegalInstrument to convert
        db: Database session

    Returns:
        GeoLegalEvent or None if conversion fails
    """
    try:
        # Check publication gate
        from app.review.publication_gate import (
            assert_legal_instrument_publication_ready,
        )

        try:
            assert_legal_instrument_publication_ready(instrument, db)
        except Exception as e:
            logger.debug(f"Instrument {instrument.id} failed publication gate: {e}")
            return None

        # Legal instruments typically don't have geographic coordinates
        # They may have jurisdiction information but not specific lat/lng
        # For now, skip materialization if no coordinates
        if not instrument.jurisdiction:
            logger.warning(f"LegalInstrument {instrument.id} has no jurisdiction")
            return None

        # Get source information
        source_ids = []
        if instrument.source_snapshot_id:
            source_ids.append(str(instrument.source_snapshot_id))

        # Build tags
        tags = ["legislation_event"]
        if instrument.instrument_type:
            tags.append(instrument.instrument_type)

        return GeoLegalEvent(
            id=f"legal:{instrument.id}",
            event_type="legislation_event",
            title=instrument.title or f"Legal Instrument {instrument.id}",
            description=instrument.summary,
            lat=None,  # Legal instruments typically jurisdictional, not point-based
            lng=None,
            location_name=instrument.jurisdiction,
            occurred_at=instrument.enacted_date,
            published_at=instrument.created_at,
            jurisdiction=instrument.jurisdiction,
            province=None,
            country="Canada",
            source_ids=source_ids,
            evidence_ids=source_ids.copy(),
            claim_ids=[],
            confidence=0.9,  # Official legal sources have high confidence
            confidence_label=get_confidence_label(0.9),
            review_status="approved",
            publish_status="public_safe",
            tags=tags,
            metadata={
                "instrument_id": instrument.id,
                "instrument_type": instrument.instrument_type,
                "public_visibility": instrument.public_visibility,
            },
        )
    except Exception as e:
        logger.error(f"Failed to materialize instrument {instrument.id}: {e}", exc_info=True)
        return None


def materialize_all_events(db: Session) -> list[GeoLegalEvent]:
    """Materialize all events from various sources into GeoLegalEvent format.

    This is the main entry point for the materialization process. It queries
    existing Event, CrimeIncident, MemoryClaim, and LegalInstrument tables and
    converts them to GeoLegalEvent format.

    Args:
        db: Database session

    Returns:
        List of GeoLegalEvent objects
    """
    events = []

    # Materialize court events
    court_events = db.query(Event).limit(DEFAULT_QUERY_LIMIT).all()
    for event in court_events:
        geo_event = materialize_from_event(event, db)
        if geo_event:
            events.append(geo_event)

    # Materialize crime incidents
    crime_incidents = (
        db.query(CrimeIncident)
        .filter(CrimeIncident.is_public.is_(True))
        .limit(DEFAULT_QUERY_LIMIT)
        .all()
    )
    for incident in crime_incidents:
        geo_event = materialize_from_crime_incident(incident, db)
        if geo_event:
            events.append(geo_event)

    # Materialize memory claims (only approved ones)
    approved_claims = (
        db.query(MemoryClaim)
        .filter(MemoryClaim.review_status == "approved")
        .limit(DEFAULT_QUERY_LIMIT // 2)
        .all()
    )
    for claim in approved_claims:
        geo_event = materialize_from_memory_claim(claim, db)
        if geo_event:
            events.append(geo_event)

    # Materialize legal instruments
    legal_instruments = (
        db.query(LegalInstrument)
        .filter(LegalInstrument.is_public.is_(True))
        .limit(DEFAULT_QUERY_LIMIT // 2)
        .all()
    )
    for instrument in legal_instruments:
        geo_event = materialize_from_legal_instrument(instrument, db)
        if geo_event:
            events.append(geo_event)

    logger.info(f"Materialized {len(events)} GeoLegalEvent objects")
    return events
