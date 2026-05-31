from datetime import date
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.redaction import redact_private_data
from app.models.entities import (
    Case,
    CaseParty,
    Court,
    CrimeIncident,
    Defendant,
    Event,
    EventDefendant,
    EventSource,
    LegalInstrument,
    LegalSource,
    Location,
)
from app.policies.publication_policy import (
    PUBLIC_REVIEW_STATUSES,
    entity_public_visibility,
)
from app.schemas.api import EventOut
from app.services.constants import OUTCOME_UNKNOWN
from app.services.publish_rules import UNSAFE_MAP_PRECISIONS

CRIME_INCIDENT_DISCLAIMER = (
    "Reported incident; not proof of guilt or conviction. "
    "Locations represent a general public area, not an exact incident point, "
    "and records may change due to late reporting, reclassification, "
    "correction, or unfounded reports."
)

_REDACTION_LABEL_RE = re.compile(r"\[REDACTED [^\]]+\]", re.IGNORECASE)
_CASE_CAPTION_RE = re.compile(r"(?:\bv\.|\bvs\.|\bversus\b)", re.IGNORECASE)
_UNSAFE_PUBLIC_TERMS_RE = re.compile(
    r"\b(?:suspect|victim|address|residence|home|dob"
    r"|date of birth|family|apartment|minor|juvenile)\b",
    re.IGNORECASE,
)


def event_options():
    return (
        selectinload(Event.court).selectinload(Court.location),
        selectinload(Event.judge),
        selectinload(Event.case)
        .selectinload(Case.parties)
        .selectinload(CaseParty.defendant),
        selectinload(Event.primary_location),
        selectinload(Event.defendant_links).selectinload(EventDefendant.defendant),
        selectinload(Event.source_links).selectinload(EventSource.source),
        selectinload(Event.outcomes),
    )


def case_options():
    return (selectinload(Case.parties).selectinload(CaseParty.defendant),)


def is_mappable(location: Location | None) -> bool:
    if location is None:
        return False
    if location.location_type in ("court_placeholder", "unmapped_court"):
        return False
    if location.latitude is None or location.longitude is None:
        return False
    return location.latitude != 0.0 and location.longitude != 0.0


def is_public_event(event: Event | None) -> bool:
    return bool(
        event
        and entity_public_visibility(event)
        and event.review_status in PUBLIC_REVIEW_STATUSES
    )


def is_public_source(source: LegalSource | None) -> bool:
    return bool(
        source
        and entity_public_visibility(source)
        and source.review_status in PUBLIC_REVIEW_STATUSES
    )


def is_public_crime_incident(incident: CrimeIncident | None) -> bool:
    return bool(
        incident
        and entity_public_visibility(incident)
        and incident.review_status in PUBLIC_REVIEW_STATUSES
    )


def is_public_crime_incident_mappable(incident: CrimeIncident) -> bool:
    if not is_public_crime_incident(incident):
        return False
    if incident.latitude_public is None or incident.longitude_public is None:
        return False
    if incident.latitude_public == 0.0 or incident.longitude_public == 0.0:
        return False
    # Block any coordinate precision that could identify a private address.
    prec = (incident.precision_level or "").lower()
    if prec in UNSAFE_MAP_PRECISIONS:
        return False
    # Secondary substring guard for unlisted labels that contain unsafe words.
    if "exact" in prec or "address" in prec or "residence" in prec or "rooftop" in prec:
        return False
    return True


def filtered_events_query(
    start: date | None,
    end: date | None,
    court_id: int | None,
    judge_id: int | None,
    event_type: str | None,
    repeat_offender_indicator: bool | None,
    verified_only: bool,
    source_type: str | None,
    limit: int | None = None,
    offset: int = 0,
):
    stmt = select(Event).options(*event_options()).join(Event.primary_location)
    stmt = stmt.where(
        Event.public_visibility.is_(True),
        Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
    )
    if source_type:
        stmt = (
            stmt.join(Event.source_links)
            .join(LegalSource)
            .where(
                LegalSource.source_type == source_type,
                LegalSource.public_visibility.is_(True),
                LegalSource.review_status.in_(PUBLIC_REVIEW_STATUSES),
            )
        )
    if start:
        stmt = stmt.where(Event.decision_date >= start)
    if end:
        stmt = stmt.where(Event.decision_date <= end)
    if court_id:
        stmt = stmt.where(Event.court_id == court_id)
    if judge_id:
        stmt = stmt.where(Event.judge_id == judge_id)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if repeat_offender_indicator is not None:
        stmt = stmt.where(Event.repeat_offender_indicator == repeat_offender_indicator)
    if verified_only:
        stmt = stmt.where(Event.verified_flag.is_(True))
    stmt = stmt.order_by(Event.decision_date.desc().nullslast(), Event.id.desc())
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def entity_by_type(db: Session, entity_type: str, entity_id: str):
    if entity_type == "event":
        return db.scalar(
            select(Event).options(*event_options()).where(Event.event_id == entity_id)
        ) or (db.get(Event, int(entity_id)) if entity_id.isdigit() else None)
    if entity_type == "crime_incident":
        return db.get(CrimeIncident, int(entity_id)) if entity_id.isdigit() else None
    if entity_type == "source":
        return db.scalar(
            select(LegalSource).where(LegalSource.source_id == entity_id)
        ) or (db.get(LegalSource, int(entity_id)) if entity_id.isdigit() else None)
    if entity_type == "legal_instrument":
        return db.get(LegalInstrument, int(entity_id)) if entity_id.isdigit() else None
    return None


def serialize_event(event: Event) -> EventOut:
    metadata = event.classifier_metadata or {}
    is_location_mappable = is_mappable(event.primary_location)
    return EventOut(
        event_id=event.event_id,
        court_id=event.court_id,
        judge_id=event.judge_id,
        case_id=event.case_id,
        primary_location_id=event.primary_location_id,
        event_type=event.event_type,
        event_subtype=event.event_subtype,
        decision_result=event.decision_result,
        decision_date=event.decision_date,
        posted_date=event.posted_date,
        title=sanitize_event_text(event.title, event, "Reviewed legal event"),
        summary=sanitize_event_text(
            event.summary, event, "Reviewed public legal summary."
        ),
        repeat_offender_indicator=event.repeat_offender_indicator,
        repeat_offender_indicators=metadata.get("repeat_offender_indicators") or [],
        verification_status=metadata.get("verification_status")
        or ("indicator_only" if event.repeat_offender_indicator else "not_indicated"),
        source_excerpt=sanitize_source_excerpt(metadata.get("source_excerpt"), event),
        is_mappable=is_location_mappable,
        location_status="mapped" if is_location_mappable else "court_location_pending",
        verified_flag=event.verified_flag,
        source_quality=event.source_quality,
        last_verified_at=event.last_verified_at,
        review_status=event.review_status,
        court=event.court,
        judge=event.judge,
        defendants=[
            {
                "id": link.defendant.id,
                "anonymized_id": link.defendant.anonymized_id,
                "display_label": link.defendant.anonymized_id,
            }
            for link in event.defendant_links
        ],
        sources=[
            source_to_public_dict(link.source, event)
            for link in event.source_links
            if is_public_source(link.source)
        ],
        outcomes=event.outcomes,
        outcome_status=None if event.outcomes else OUTCOME_UNKNOWN,
    )


def event_to_geojson_feature(event: Event) -> dict:
    loc = event.primary_location
    judge = event.judge
    court = event.court
    case = event.case
    public_sources = [
        link for link in event.source_links if is_public_source(link.source)
    ]
    news_sources = [
        s for s in public_sources if s.source.source_type in {"news", "news_article"}
    ]
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [loc.longitude, loc.latitude]},
        "properties": {
            "record_type": "court_event",
            "event_id": event.event_id,
            "judge_id": judge.id if judge else None,
            "judge_name": judge.name if judge else "Unknown judge",
            "court_id": court.id if court else None,
            "court_name": court.name if court else None,
            "location_id": loc.id,
            "location_name": loc.name,
            "event_type": event.event_type,
            "event_date": (
                event.decision_date.isoformat() if event.decision_date else None
            ),
            "case_id": case.id if case else None,
            "case_name": sanitize_case_caption(case, event) if case else None,
            "case_number": case.docket_number if case else None,
            "verified_flag": bool(event.verified_flag),
            "repeat_offender_indicator": bool(event.repeat_offender_indicator),
            "review_status": event.review_status,
            "public_visibility": entity_public_visibility(event),
            "location_status": "mapped",
            "is_mappable": True,
            "title": sanitize_event_text(event.title, event, "Reviewed legal event"),
            "decision_date": (
                event.decision_date.isoformat() if event.decision_date else None
            ),
            "court": court.name if court else None,
            "judge": judge.name if judge else None,
            "source_quality": event.source_quality,
            "defendants": [
                link.defendant.anonymized_id for link in event.defendant_links
            ],
            "source_count": len(public_sources),
            "has_news": bool(news_sources),
            "has_incident_links": False,
            "disclaimer": "Court record. Does not imply the judge caused later events.",
        },
    }


def crime_incident_to_geojson_feature(incident: CrimeIncident) -> dict:
    public_struct_sources = (
        [link for link in incident.source_links if is_public_source(link.source)]
        if hasattr(incident, "source_links")
        else []
    )
    verified_court_links = (
        [
            link
            for link in incident.event_links
            if link.relationship_status == "verified_source_link"
        ]
        if hasattr(incident, "event_links")
        else []
    )
    source_count = (
        len(public_struct_sources)
        if public_struct_sources
        else (1 if incident.source_url else 0)
    )
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [incident.longitude_public, incident.latitude_public],
        },
        "properties": {
            "record_type": "reported_incident",
            "incident_id": incident.id,
            "incident_type": sanitize_public_text(
                incident.incident_type, "Reported incident"
            ),
            "incident_category": incident.incident_category,
            "reported_at": (
                incident.reported_at.isoformat() if incident.reported_at else None
            ),
            "occurred_at": (
                incident.occurred_at.isoformat() if incident.occurred_at else None
            ),
            "city": incident.city,
            "province_state": incident.province_state,
            "country": incident.country,
            "area_label": (
                sanitize_public_text(incident.public_area_label, "General area")
                if incident.public_area_label
                else None
            ),
            "precision_level": incident.precision_level,
            "source_name": sanitize_public_text(
                incident.source_name, "Official open data source"
            ),
            "source_url": incident.source_url,
            "verification_status": incident.verification_status,
            "review_status": incident.review_status,
            "public_visibility": entity_public_visibility(incident),
            "source_count": source_count,
            "has_news": False,
            "has_court_links": bool(verified_court_links),
            "is_aggregate": bool(incident.is_aggregate),
            "disclaimer": CRIME_INCIDENT_DISCLAIMER,
        },
    }


def case_to_public_dict(case: Case, event: Event | None = None) -> dict:
    return {
        "id": case.id,
        "court_id": case.court_id,
        "docket_number": case.docket_number,
        "caption": sanitize_case_caption(case, event),
        "case_type": case.case_type,
        "filed_date": case.filed_date,
        "terminated_date": case.terminated_date,
    }


def source_to_public_dict(source: LegalSource, event: Event | None = None) -> dict:
    linked_event = event or _first_linked_event(source)
    return {
        "id": source.id,
        "source_id": source.source_id,
        "source_type": source.source_type,
        "title": sanitize_source_title(source, linked_event),
        "url": source.url,
        "source_quality": source.source_quality,
        "verified_flag": source.verified_flag,
        "review_status": source.review_status,
    }


def source_panel_payload(entity_type: str, entity) -> dict:
    if isinstance(entity, Event):
        sources = [
            {
                "source_name": sanitize_source_title(link.source, entity),
                "source_type": link.source.source_type,
                "source_url": link.source.url,
                "retrieved_at": (
                    link.source.retrieved_at.isoformat()
                    if link.source.retrieved_at
                    else None
                ),
                "published_at": None,
                "quoted_excerpt": sanitize_source_excerpt(
                    (entity.classifier_metadata or {}).get("source_excerpt"), entity
                ),
                "verification_status": link.source.review_status,
                "trust_reason": "Linked court/legal source for this event.",
                "reviewed_by": entity.reviewed_by,
                "reviewed_at": (
                    entity.reviewed_at.isoformat() if entity.reviewed_at else None
                ),
                "review_status": entity.review_status,
            }
            for link in entity.source_links
            if is_public_source(link.source)
        ]
        return {
            "entity_type": "event",
            "entity_id": entity.event_id,
            "review_status": entity.review_status,
            "sources": sources,
        }
    if isinstance(entity, CrimeIncident):
        # Prefer structured source_links where linked source is public
        public_struct_sources = (
            [link for link in entity.source_links if is_public_source(link.source)]
            if hasattr(entity, "source_links")
            else []
        )

        if public_struct_sources:
            # Use CrimeIncidentSource links when available
            sources = [
                {
                    "source_name": sanitize_source_title(link.source, None),
                    "source_type": link.source.source_type,
                    "source_url": link.source.url,
                    "retrieved_at": (
                        link.source.retrieved_at.isoformat()
                        if link.source.retrieved_at
                        else None
                    ),
                    "published_at": None,
                    "quoted_excerpt": None,
                    "verification_status": link.source.review_status,
                    "trust_reason": "Linked public source for this incident.",
                    "reviewed_by": link.source.reviewed_by,
                    "reviewed_at": (
                        link.source.reviewed_at.isoformat()
                        if link.source.reviewed_at
                        else None
                    ),
                    "review_status": link.source.review_status,
                }
                for link in public_struct_sources
            ]
        else:
            # Fall back to top-level source fields only if no structured links exist
            sources = [
                {
                    "source_name": sanitize_public_text(
                        entity.source_name, "Official open data source"
                    ),
                    "source_type": "official_police_open_data",
                    "source_url": entity.source_url,
                    "retrieved_at": (
                        entity.data_last_seen_at.isoformat()
                        if entity.data_last_seen_at
                        else None
                    ),
                    "published_at": (
                        entity.reported_at.isoformat() if entity.reported_at else None
                    ),
                    "quoted_excerpt": None,
                    "verification_status": entity.verification_status,
                    "trust_reason": (
                        "Official reported-incident source;"
                        " not proof of guilt or conviction."
                    ),
                    "reviewed_by": entity.reviewed_by,
                    "reviewed_at": (
                        entity.reviewed_at.isoformat() if entity.reviewed_at else None
                    ),
                    "review_status": entity.review_status,
                }
            ]

        return {
            "entity_type": "crime_incident",
            "entity_id": entity.id,
            "review_status": entity.review_status,
            "sources": sources,
        }
    return {
        "entity_type": "source",
        "entity_id": entity.source_id,
        "review_status": entity.review_status,
        "sources": [
            {
                "source_name": sanitize_source_title(
                    entity, _first_linked_event(entity)
                ),
                "source_type": entity.source_type,
                "source_url": entity.url,
                "retrieved_at": (
                    entity.retrieved_at.isoformat() if entity.retrieved_at else None
                ),
                "published_at": None,
                "quoted_excerpt": None,
                "verification_status": entity.review_status,
                "trust_reason": "Reviewed source record.",
                "reviewed_by": entity.reviewed_by,
                "reviewed_at": (
                    entity.reviewed_at.isoformat() if entity.reviewed_at else None
                ),
                "review_status": entity.review_status,
            }
        ],
    }


def sanitize_event_text(text: str | None, event: Event, fallback: str) -> str:
    return sanitize_public_text(
        _replace_known_defendant_names(text, _event_name_pairs(event)), fallback
    )


def sanitize_source_excerpt(text: str | None, event: Event | None = None) -> str | None:
    if not text:
        return None
    safe_text = _replace_known_defendant_names(
        text, _event_name_pairs(event) if event else []
    )
    return sanitize_public_text(
        safe_text, "Reviewed source excerpt redacted for privacy."
    )


def sanitize_case_caption(case: Case, event: Event | None = None) -> str:
    labels = _event_labels(event) if event else _case_labels(case)
    pairs = _event_name_pairs(event) if event else _case_name_pairs(case)
    caption = _replace_known_defendant_names(case.caption, pairs)
    if caption != (case.caption or ""):
        return sanitize_public_text(caption, "Reviewed case record")
    if _looks_like_case_caption(caption):
        if labels:
            return f"Reviewed case record ({', '.join(labels)})"
        return "Reviewed case record"
    return sanitize_public_text(caption, "Reviewed case record")


def sanitize_source_title(source: LegalSource, event: Event | None = None) -> str:
    pairs = _event_name_pairs(event) if event else []
    title = _replace_known_defendant_names(source.title, pairs)
    if title != (source.title or ""):
        return sanitize_public_text(title, "Reviewed legal source")
    if _looks_like_case_caption(title):
        return "Reviewed legal source"
    return sanitize_public_text(title, "Reviewed legal source")


def _first_linked_event(source: LegalSource) -> Event | None:
    for link in source.event_links:
        if link.event:
            return link.event
    return None


def sanitize_public_text(text: str | None, fallback: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return fallback
    redaction = redact_private_data(compact, None, "public")
    safe = _REDACTION_LABEL_RE.sub("[redacted]", redaction.redacted_text)
    if redaction.privacy_risk and _UNSAFE_PUBLIC_TERMS_RE.search(safe):
        return fallback
    if _UNSAFE_PUBLIC_TERMS_RE.search(safe):
        return fallback
    return safe[:1000] or fallback


def _event_labels(event: Event | None) -> list[str]:
    if not event:
        return []
    return [link.defendant.anonymized_id for link in event.defendant_links]


def _case_labels(case: Case) -> list[str]:
    labels: list[str] = []
    for party in case.parties:
        if party.defendant:
            labels.append(party.defendant.anonymized_id)
    return labels


def _event_name_pairs(event: Event | None) -> list[tuple[str, str]]:
    if not event:
        return []
    pairs: list[tuple[str, str]] = []
    for link in event.defendant_links:
        pairs.extend(_defendant_name_pairs(link.defendant))
    if event.case:
        pairs.extend(_case_name_pairs(event.case))
    return _dedupe_pairs(pairs)


def _case_name_pairs(case: Case) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for party in case.parties:
        if party.defendant:
            pairs.extend(_defendant_name_pairs(party.defendant))
            if party.public_name:
                pairs.append((party.public_name, party.defendant.anonymized_id))
    return _dedupe_pairs(pairs)


def _defendant_name_pairs(defendant: Defendant) -> list[tuple[str, str]]:
    if not defendant.public_name:
        return []
    return [(defendant.public_name, defendant.anonymized_id)]


def _dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for original, replacement in pairs:
        key = (original, replacement)
        if original and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _replace_known_defendant_names(
    text: str | None, pairs: list[tuple[str, str]]
) -> str:
    safe = text or ""
    for original, replacement in pairs:
        if not original:
            continue
        safe = re.sub(
            rf"\b{re.escape(original)}\b", replacement, safe, flags=re.IGNORECASE
        )
    return safe


def _looks_like_case_caption(value: str | None) -> bool:
    return bool(value and _CASE_CAPTION_RE.search(value))
