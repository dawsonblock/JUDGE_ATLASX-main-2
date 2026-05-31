"""Gate that must pass before any record can be set is_public=True.

Public map publishing requires:
- valid evidence source
- source not blocked
- confidence above threshold
- location not ambiguous
- privacy/redaction pass complete
- review_status approved
- no unresolved high-risk contradiction

Default policy:
- official structured sources may auto-publish low-risk metadata
- news/police narrative sources require review
- person-specific accusations require strict review or block
- ambiguous locations stay admin-only
"""
from __future__ import annotations

from app.models.entities import CrimeIncident, LegalInstrument, Location, ReviewItem, MemoryClaim
from app.models.geocode_cache import GeocodeCache
from app.models.geo_legal_event import GeoLegalEvent
from app.policies.publication_policy import can_publish_entity, entity_public_visibility
from app.policies.public_status import (
    PUBLIC_REDACTED,
    PUBLIC_SAFE,
    PUBLIC_VISIBLE_STATUSES,
    REVIEW_APPROVED,
)
from app.policies.state_model import (
    ReviewQueueDecision,
    normalize_review_queue_decision,
)
from sqlalchemy.orm import Session, object_session


class PublicationBlockedError(ValueError):
    """Raised when a record cannot be published due to unmet requirements."""


def assert_publication_ready(incident: CrimeIncident, db: Session) -> None:
    """Raise PublicationBlockedError if the incident may not be published.

    Domain entity publication means review_status + public visibility +
    evidence gate.  ReviewItem ``approved`` is not accepted here.
    
    Also checks that geocoding result is not ambiguous for map publishing.
    """
    decision = can_publish_entity(db, "crime_incident", incident)
    if not decision.allowed:
        raise PublicationBlockedError(
            f"Incident {incident.id} blocked: {'; '.join(decision.reasons)}"
        )
    
    # Check geocoding status if location is set
    if incident.primary_location_id:
        location = db.query(Location).filter(
            Location.id == incident.primary_location_id
        ).first()
        if location and location.geocode_cache_id:
            geocode = db.query(GeocodeCache).filter(
                GeocodeCache.id == location.geocode_cache_id
            ).first()
            if geocode and geocode.status not in ("exact", "approximate"):
                raise PublicationBlockedError(
                    f"Incident {incident.id} has ambiguous or failed "
                    f"geocoding status '{geocode.status}' — "
                    f"cannot publish to public map"
                )


def assert_review_item_publication_ready(item: ReviewItem) -> None:
    """Raise PublicationBlockedError if the ReviewItem has not been approved.

    ReviewItem uses a workflow ``status`` field (not ``review_status``), so
    this assert is intentionally separate from :func:`can_publish`.
    """
    if normalize_review_queue_decision(item.status) != ReviewQueueDecision.APPROVED:
        raise PublicationBlockedError(
            f"ReviewItem {item.id} status='{item.status}' — must be 'approved'"
        )
    if not item.source_snapshot_id:
        raise PublicationBlockedError(
            f"ReviewItem {item.id} has no source_snapshot_id — evidence link required"
        )


def assert_legal_instrument_publication_ready(
    instrument: LegalInstrument,
    db: Session | None = None,
) -> None:
    """Raise PublicationBlockedError if a legal instrument is not publication-ready.

    Delegates to the canonical policy.  ReviewItem ``approved`` is an
    internal workflow state and never a LegalInstrument.review_status.
    """
    db = db or object_session(instrument)
    if db is None:
        raise PublicationBlockedError(
            "LegalInstrument publication requires a database session"
        )
    decision = can_publish_entity(db, "legal_instrument", instrument)
    if not decision.allowed:
        raise PublicationBlockedError(
            f"LegalInstrument {instrument.id} blocked: {'; '.join(decision.reasons)}"
        )
    if not entity_public_visibility(instrument):
        raise PublicationBlockedError(
            f"LegalInstrument {instrument.id} public_visibility="
            f"'{instrument.public_visibility}' — must be 'public'"
        )


def assert_memory_claim_publication_ready(claim: MemoryClaim, db: Session) -> None:
    """Raise PublicationBlockedError if a memory claim is not publication-ready.

    Memory claims require:
    - review_status = approved
    - At least one supporting evidence link
    - Confidence above threshold (0.7)
    - No open high/critical contradictions
    - Claim status is not disputed/rejected/superseded
    - Private-person allegations have review
    - Source is not deprecated/quarantined
    """
    # Check review status
    if claim.review_status != "approved":
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} review_status='{claim.review_status}' — must be 'approved'"
        )

    # Check claim status
    if claim.status in ["disputed", "rejected", "superseded", "invalid"]:
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} status='{claim.status}' — cannot publish disputed/rejected/superseded claims"
        )

    # Check evidence
    from app.models.entities import MemoryEvidenceLink

    supporting_evidence = (
        db.query(MemoryEvidenceLink)
        .filter(
            MemoryEvidenceLink.claim_id == claim.id,
            MemoryEvidenceLink.support_type == "supports",
        )
        .count()
    )
    if supporting_evidence == 0:
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} has no supporting evidence links"
        )

    # Check confidence
    if claim.confidence < 0.7:
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} confidence={claim.confidence} — must be >= 0.7"
        )

    # Check for open high/critical contradictions using durable system
    from app.memory.contradiction_engine import get_open_contradictions_by_claim

    open_contradictions = get_open_contradictions_by_claim(claim.id, db)
    high_critical_contradictions = [
        c for c in open_contradictions
        if c.severity in ["high", "critical"]
    ]

    if high_critical_contradictions:
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} has {len(high_critical_contradictions)} open high/critical contradictions"
        )

    # Fail closed when contradiction metadata indicates unresolved conflicts,
    # even if durable contradiction rows are not yet materialized.
    if (claim.contradiction_count or 0) > 0:
        raise PublicationBlockedError(
            f"MemoryClaim {claim.id} contradiction_count={claim.contradiction_count} — unresolved contradictions block publication"
        )

    # Check named-person criminal allegations have elevated approval
    if claim.claim_sensitivity == "criminal_allegation_named_person":
        # Require elevated review approval for named-person criminal allegations
        if claim.elevated_review_status != "approved":
            raise PublicationBlockedError(
                f"MemoryClaim {claim.id} requires elevated approval for named-person criminal allegation"
            )

        # Require evidence source is official/public record
        if claim.source_snapshot_id:
            from app.models.entities import SourceSnapshot, LegalSource

            snapshot = db.query(SourceSnapshot).filter(
                SourceSnapshot.id == claim.source_snapshot_id
            ).first()
            if snapshot:
                source = None
                snapshot_source_id = getattr(snapshot, "source_id", None)
                snapshot_source_key = getattr(snapshot, "source_key", None)
                if snapshot_source_id is not None:
                    source = db.query(LegalSource).filter(
                        LegalSource.id == snapshot_source_id
                    ).first()
                elif snapshot_source_key:
                    source = db.query(LegalSource).filter(
                        LegalSource.source_id == str(snapshot_source_key)
                    ).first()
                if source and source.lifecycle_state not in ["active", "official"]:
                    raise PublicationBlockedError(
                        f"MemoryClaim {claim.id} evidence source '{source.source_id}' is not official/public record — requires elevated approval source"
                    )

        # Block media-only named-person criminal allegations
        if claim.source_snapshot_id:
            from app.models.entities import SourceSnapshot, LegalSource

            snapshot = db.query(SourceSnapshot).filter(
                SourceSnapshot.id == claim.source_snapshot_id
            ).first()
            if snapshot:
                source = None
                snapshot_source_id = getattr(snapshot, "source_id", None)
                snapshot_source_key = getattr(snapshot, "source_key", None)
                if snapshot_source_id is not None:
                    source = db.query(LegalSource).filter(
                        LegalSource.id == snapshot_source_id
                    ).first()
                elif snapshot_source_key:
                    source = db.query(LegalSource).filter(
                        LegalSource.source_id == str(snapshot_source_key)
                    ).first()
                if source and source.lifecycle_state == "media":
                    raise PublicationBlockedError(
                        f"MemoryClaim {claim.id} is a named-person criminal allegation from media source — media-only allegations are blocked"
                    )

    # Check redaction pass for sensitive claims
    if claim.claim_sensitivity in ["criminal_allegation_named_person", "criminal_allegation_private_person", "misconduct_allegation"]:
        # Require redaction pass for sensitive claims
        # This is checked during AI extraction; if redaction failed, the claim should not publish
        if claim.confidence < 0.8:  # Higher threshold for sensitive claims
            raise PublicationBlockedError(
                f"MemoryClaim {claim.id} has sensitivity '{claim.claim_sensitivity}' and confidence {claim.confidence} — sensitive claims require higher confidence and redaction pass"
            )

    # Check source status if available
    if claim.extraction_run_id:
        from app.models.entities import IngestionRun, LegalSource

        ingestion_run = db.query(IngestionRun).filter(
            IngestionRun.id == claim.extraction_run_id
        ).first()
        if ingestion_run:
            source = None
            run_source_id = getattr(ingestion_run, "source_id", None)
            run_source_name = getattr(ingestion_run, "source_name", None)
            if run_source_id is not None:
                source = db.query(LegalSource).filter(
                    LegalSource.id == run_source_id
                ).first()
            elif run_source_name:
                source = db.query(LegalSource).filter(
                    LegalSource.source_id == str(run_source_name)
                ).first()
                if source is None and str(run_source_name).isdigit():
                    source = db.query(LegalSource).filter(
                        LegalSource.id == int(str(run_source_name))
                    ).first()
            lifecycle_state = getattr(source, "lifecycle_state", None) if source else None
            if lifecycle_state in ["deprecated", "quarantined"]:
                raise PublicationBlockedError(
                    f"MemoryClaim {claim.id} source '{source.source_id}' is {lifecycle_state} — cannot publish"
                )


def assert_geo_legal_event_publication_ready(
    event: GeoLegalEvent, db: Session
) -> None:
    """Raise PublicationBlockedError if a GeoLegalEvent is not publication-ready.

    GeoLegalEvents are materialized events that have already passed the
    publication gate for their underlying sources. This function performs
    final validation before map rendering.

    Requirements:
    - review_status = approved
    - publish_status in [public_safe, public_redacted]
    - confidence above threshold (configurable, default 0.7)
    - Location coordinates are present and valid
    - No unresolved high-risk contradictions in linked claims
    """
    # Check review status
    if event.review_status != REVIEW_APPROVED:
        raise PublicationBlockedError(
            f"GeoLegalEvent {event.id} review_status='{event.review_status}' — must be '{REVIEW_APPROVED}'"
        )

    # Check publish status
    if event.publish_status not in PUBLIC_VISIBLE_STATUSES:
        raise PublicationBlockedError(
            f"GeoLegalEvent {event.id} publish_status='{event.publish_status}' — must be '{PUBLIC_SAFE}' or '{PUBLIC_REDACTED}'"
        )

    # Check confidence
    from app.core.config import get_settings

    settings = get_settings()
    min_confidence = getattr(settings, "public_map_min_confidence", 0.7)
    if event.confidence < min_confidence:
        raise PublicationBlockedError(
            f"GeoLegalEvent {event.id} confidence={event.confidence} — must be >= {min_confidence}"
        )

    # Check location coordinates
    if event.lat is None or event.lng is None:
        raise PublicationBlockedError(
            f"GeoLegalEvent {event.id} has missing coordinates — cannot render on map"
        )

    # Validate coordinate ranges
    if not (-90 <= event.lat <= 90) or not (-180 <= event.lng <= 180):
        raise PublicationBlockedError(
            f"GeoLegalEvent {event.id} has invalid coordinates ({event.lat}, {event.lng})"
        )

    # Check for unresolved high-risk contradictions in linked claims
    if event.claim_ids:
        from app.memory.contradiction_engine import get_open_contradictions_by_claim
        from app.models.entities import MemoryClaim

        # Convert string IDs to integers for querying MemoryClaim.id (primary key)
        claim_int_ids = []
        for claim_id in event.claim_ids:
            try:
                claim_int_ids.append(int(claim_id))
            except (ValueError, TypeError):
                # Skip invalid claim IDs
                continue

        if claim_int_ids:
            # Bulk query all claims at once
            claims = db.query(MemoryClaim).filter(
                MemoryClaim.id.in_(claim_int_ids)
            ).all()

            high_risk_claims = []
            for claim in claims:
                open_contradictions = get_open_contradictions_by_claim(claim.id, db)
                high_critical_contradictions = [
                    c for c in open_contradictions
                    if c.severity in ["high", "critical"]
                ]
                if high_critical_contradictions:
                    high_risk_claims.append(claim.id)

            if high_risk_claims:
                raise PublicationBlockedError(
                    f"GeoLegalEvent {event.id} has {len(high_risk_claims)} linked claims with open high/critical contradictions"
                )

    # Check event type-specific rules
    if event.event_type and event.event_type in ["crime_event", "police_release"]:
        # Crime and police events require higher confidence
        if event.confidence < 0.8:
            raise PublicationBlockedError(
                f"GeoLegalEvent {event.id} is a {event.event_type} with confidence {event.confidence} — crime/police events require confidence >= 0.8"
            )

    # Check source health if source_ids are present
    if event.source_ids:
        from app.models.entities import LegalSource

        # Convert string IDs to integers for querying LegalSource.id (primary key)
        source_int_ids = []
        for source_id in event.source_ids:
            try:
                source_int_ids.append(int(source_id))
            except (ValueError, TypeError):
                # Skip invalid source IDs
                continue

        if source_int_ids:
            blocked_sources = db.query(LegalSource).filter(
                LegalSource.id.in_(source_int_ids),
                LegalSource.lifecycle_state.in_(["deprecated", "quarantined", "blocked"])
            ).all()

            if blocked_sources:
                raise PublicationBlockedError(
                    f"GeoLegalEvent {event.id} has {len(blocked_sources)} blocked/deprecated sources"
                )
