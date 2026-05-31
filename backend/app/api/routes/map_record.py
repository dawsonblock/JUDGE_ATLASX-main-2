"""GET /api/map/record/{record_type}/{record_id}

Returns a full public evidence bundle for a single map dot.
Safety rules:
- Only records in PUBLIC_REVIEW_STATUSES with public visibility are returned.
- related_* arrays only include entries with relationship_status == "verified_source_link".
- All text is passed through sanitize_* helpers.
- No victim names, suspect names, or exact private addresses.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.entities import (
    CrimeIncident,
    CrimeIncidentEventLink,
    CrimeIncidentSource,
    Event,
    LegalSource,
)
from app.policies.publication_policy import can_show_public_entity
from app.serializers.public import (
    event_options,
    is_public_crime_incident,
    is_public_event,
    is_public_source,
    sanitize_case_caption,
    sanitize_event_text,
    sanitize_public_text,
)

router = APIRouter()

COURT_EVENT_DISCLAIMER = "Court record. Does not imply the judge caused later events."
INCIDENT_DISCLAIMER = "Reported incident. Not proof of guilt or conviction."
NEWS_CONTEXT_NOTE = "News links are context unless marked as verified source links."

_NEWS_SOURCE_TYPES = {"news", "news_article"}
_OFFICIAL_SOURCE_TYPES = {
    "official",
    "court_record",
    "open_data",
    "official_police_open_data",
}

VERIFIED_LINK = "verified_source_link"


def _serialize_source_link(
    source: LegalSource, supports_claim: str | None = None
) -> dict:
    return {
        "label": sanitize_public_text(source.title, "Reviewed source"),
        "url": source.url,
        "source_type": source.source_type,
        "supports_claim": supports_claim or "",
        "retrieved_at": (
            source.retrieved_at.isoformat() if source.retrieved_at else None
        ),
        "snapshot_hash": source.url_hash,
        "is_context_only": source.source_type in _NEWS_SOURCE_TYPES,
    }


def _incident_options():
    return (
        selectinload(CrimeIncident.source_links).selectinload(
            CrimeIncidentSource.source
        ),
        selectinload(CrimeIncident.event_links).selectinload(
            CrimeIncidentEventLink.event
        ),
        selectinload(CrimeIncident.source_snapshot),
    )


@router.get("/api/map/record/{record_type}/{record_id}")
def map_record_detail(
    record_type: str,
    record_id: str,
    db: Session = Depends(get_db),
):
    if record_type == "court_event":
        return _court_event_detail(record_id, db)
    if record_type == "reported_incident":
        return _incident_detail(record_id, db)
    raise HTTPException(status_code=404, detail="Unknown record_type")


def _court_event_detail(record_id: str, db: Session) -> dict:
    event = db.scalar(
        select(Event).options(*event_options()).where(Event.event_id == record_id)
    )
    if not is_public_event(event):
        raise HTTPException(status_code=404, detail="Record not found")

    judge = event.judge
    court = event.court
    case = event.case
    loc = event.primary_location

    public_sources = [
        link for link in event.source_links if is_public_source(link.source)
    ]
    source_links = [
        _serialize_source_link(link.source)
        for link in public_sources
        if link.source.source_type not in _NEWS_SOURCE_TYPES
    ]
    news_articles = [
        _serialize_source_link(link.source)
        for link in public_sources
        if link.source.source_type in _NEWS_SOURCE_TYPES
    ]

    related_incidents: list[dict] = []

    audit_date = (
        event.reviewed_at or event.updated_at
        if hasattr(event, "updated_at")
        else event.reviewed_at
    )
    return {
        "record_type": "court_event",
        "id": event.event_id,
        "title": sanitize_event_text(event.title, event, "Reviewed legal event"),
        "event_type": event.event_type,
        "event_subtype": event.event_subtype,
        "date": event.decision_date.isoformat() if event.decision_date else None,
        "court_name": court.name if court else None,
        "court_location": (
            f"{loc.city}, {loc.state}"
            if loc and loc.city
            else (loc.name if loc else None)
        ),
        "judge_name": judge.name if judge else None,
        "case_name": sanitize_case_caption(case, event) if case else None,
        "docket_number": case.docket_number if case else None,
        "summary": sanitize_event_text(
            event.summary, event, "Reviewed public legal summary."
        ),
        "source_links": source_links,
        "news_articles": news_articles,
        "related_reported_incidents": related_incidents,
        "review_status": event.review_status,
        "source_quality": event.source_quality,
        "source_count": len(source_links) + len(news_articles),
        "evidence_count": len(source_links) + len(news_articles),
        "confidence": (event.classifier_metadata or {}).get("confidence"),
        "source_tier": event.source_quality,
        "warnings": (
            ["Low classifier confidence"]
            if isinstance((event.classifier_metadata or {}).get("confidence"), float)
            and (event.classifier_metadata or {}).get("confidence") < 0.5
            else []
        ),
        "audit": {
            "review_status": event.review_status,
            "reviewed_by": event.reviewed_by,
            "reviewed_at": event.reviewed_at.isoformat() if event.reviewed_at else None,
            "last_updated": audit_date.isoformat() if audit_date else None,
        },
        "disclaimer": COURT_EVENT_DISCLAIMER,
        "news_context_note": NEWS_CONTEXT_NOTE,
    }


def _incident_detail(record_id: str, db: Session) -> dict:
    if not record_id.isdigit():
        raise HTTPException(status_code=404, detail="Record not found")
    incident = db.scalar(
        select(CrimeIncident)
        .options(*_incident_options())
        .where(CrimeIncident.id == int(record_id))
    )
    if not is_public_crime_incident(incident):
        raise HTTPException(status_code=404, detail="Record not found")
    policy = can_show_public_entity(db, "crime_incident", incident)
    if not policy.allowed:
        raise HTTPException(status_code=404, detail="Record not found")

    source_links: list[dict] = []
    news_articles: list[dict] = []

    for link in incident.source_links:
        if not is_public_source(link.source):
            continue
        entry = _serialize_source_link(link.source, link.supports_claim)
        if link.source.source_type in _NEWS_SOURCE_TYPES:
            news_articles.append(entry)
        else:
            source_links.append(entry)

    if not source_links and incident.source_url:
        source_links.append(
            {
                "label": sanitize_public_text(
                    incident.source_name, "Official open data source"
                ),
                "url": incident.source_url,
                "source_type": "official",
                "supports_claim": "",
                "retrieved_at": (
                    incident.data_last_seen_at.isoformat()
                    if incident.data_last_seen_at
                    else None
                ),
            }
        )

    related_court_records: list[dict] = []
    for link in incident.event_links:
        if link.relationship_status != VERIFIED_LINK:
            continue
        ev = link.event
        if not ev or not is_public_event(ev):
            continue
        judge = ev.judge
        case = ev.case
        _ev_url = (ev.cl_provenance or {}).get("absolute_url") or (
            ev.cl_provenance or {}
        ).get("url")
        related_court_records.append(
            {
                "event_id": ev.event_id,
                "case_name": sanitize_case_caption(case, ev) if case else None,
                "judge_name": judge.name if judge else None,
                "decision_type": ev.event_type,
                "date": ev.decision_date.isoformat() if ev.decision_date else None,
                "relationship_status": link.relationship_status,
                "url": _ev_url,
            }
        )

    audit_date = incident.reviewed_at
    return {
        "record_type": "reported_incident",
        "id": incident.id,
        "category": incident.incident_category,
        "incident_type": sanitize_public_text(
            incident.incident_type, "Reported incident"
        ),
        "date": (
            incident.occurred_at.date().isoformat()
            if incident.occurred_at
            else (
                incident.reported_at.date().isoformat()
                if incident.reported_at
                else None
            )
        ),
        "city": incident.city,
        "state_province": incident.province_state,
        "country": incident.country,
        "area_label": (
            sanitize_public_text(incident.public_area_label, "General area")
            if incident.public_area_label
            else None
        ),
        "latitude": incident.latitude_public,
        "longitude": incident.longitude_public,
        "precision_level": incident.precision_level,
        "summary": sanitize_public_text(
            incident.incident_type,
            "Reported incident from official public source.",
        ),
        "source_links": source_links,
        "news_articles": news_articles,
        "related_court_records": related_court_records,
        "review_status": incident.review_status,
        "verification_status": incident.verification_status,
        "source_count": len(source_links) + len(news_articles),
        "evidence_count": len(source_links) + len(news_articles),
        "confidence": None,
        "source_tier": (
            "official" if incident.source_url else incident.verification_status
        ),
        "warnings": ([] if related_court_records else ["No linked court record"]),
        "audit": {
            "review_status": incident.review_status,
            "reviewed_by": incident.reviewed_by,
            "reviewed_at": (
                incident.reviewed_at.isoformat() if incident.reviewed_at else None
            ),
            "last_updated": audit_date.isoformat() if audit_date else None,
        },
        "snapshot": {
            "source_snapshot_id": incident.source_snapshot_id,
            "content_hash": (
                incident.source_snapshot.content_hash
                if incident.source_snapshot
                else None
            ),
            "fetched_at": (
                incident.source_snapshot.fetched_at.isoformat()
                if incident.source_snapshot
                else None
            ),
            "source_url": (
                incident.source_snapshot.source_url
                if incident.source_snapshot
                else None
            ),
        },
        "disclaimer": INCIDENT_DISCLAIMER,
        "news_context_note": NEWS_CONTEXT_NOTE,
    }
