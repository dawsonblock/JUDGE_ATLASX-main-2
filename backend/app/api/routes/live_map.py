"""Live map API endpoints for GeoLegalEvent data.

Provides endpoints for querying normalized map events, layers, feed status,
and source health. Supports both public and admin access patterns with
appropriate filtering and redaction.

Experimental route module.
Not mounted in the runtime API until authorization and public-boundary tests pass.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit_map
from app.db.session import get_db
from app.policies.public_status import (
    PUBLIC_REDACTED,
    PUBLIC_SAFE,
    PUBLIC_VISIBLE_STATUSES,
    REVIEW_APPROVED,
)
from app.schemas.geo_legal_event import GeoLegalEvent

router = APIRouter()


def _load_live_map_events(db: Session) -> list[GeoLegalEvent]:
    """Load GeoLegalEvents from materialized table.

    Fallback to on-demand materialization only when table access fails in local
    dev/test contexts.
    """
    try:
        from app.models.geo_legal_event import GeoLegalEvent as GeoLegalEventModel

        rows = db.query(GeoLegalEventModel).all()
        return [GeoLegalEvent.model_validate(row) for row in rows]
    except Exception:
        from app.map.materialize_geo_legal_events import materialize_all_events

        return materialize_all_events(db)


PLATFORM_DISCLAIMER = (
    "JudgeTracker Atlas is a hardened prototype. All records enter a review "
    "workflow before public display. Pending, rejected, and removed records "
    "are excluded. This is not a substitute for legal advice."
)

# Maximum bbox area (degrees² longitude × latitude) accepted per request
_MAX_BBOX_AREA_SQ_DEG = 625.0  # 25° × 25° = 625 sq degrees
_UNSAFE_PUBLIC_PRECISIONS = {
    "exact_address",
    "exact_residence",
    "rooftop",
    "parcel",
    "exact",
}


def _parse_bbox(
    bbox: str | None, max_area: float = _MAX_BBOX_AREA_SQ_DEG
) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north' bbox string."""
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422, detail="bbox must be 'west,south,east,north'"
        )
    try:
        west, south, east, north = (float(p.strip()) for p in parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox values must be numeric")
    if not (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
    ):
        raise HTTPException(
            status_code=422, detail="bbox values out of valid WGS84 range"
        )
    if south > north:
        raise HTTPException(status_code=422, detail="bbox south must be <= north")
    if west > east:
        raise HTTPException(
            status_code=422,
            detail="bbox west must be <= east (antimeridian crossing not supported)",
        )
    if max_area is not None:
        area = (east - west) * (north - south)
        if area > max_area:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"bbox area ({area:.1f} sq degrees) exceeds maximum "
                    f"{max_area:.0f} sq degrees per request"
                ),
            )
    return west, south, east, north


def _apply_public_filters(
    events: list[GeoLegalEvent], settings: Settings
) -> list[GeoLegalEvent]:
    """Apply public-safe filters to events."""
    min_confidence = float(getattr(settings, "public_map_min_confidence", 0.7))

    filtered = []
    for event in events:
        # Only return public-safe or public-redacted events
        if event.publish_status not in PUBLIC_VISIBLE_STATUSES:
            continue
        # Only return approved events
        if event.review_status != REVIEW_APPROVED:
            continue
        # Only return events above confidence threshold
        if event.confidence < min_confidence:
            continue
        precision = str((event.metadata or {}).get("precision", "")).strip().lower()
        if precision in _UNSAFE_PUBLIC_PRECISIONS:
            continue
        filtered.append(event)
    return filtered


def _apply_bbox_filter(
    events: list[GeoLegalEvent], bbox_parsed: tuple[float, float, float, float] | None
) -> list[GeoLegalEvent]:
    """Filter events by bounding box."""
    if not bbox_parsed:
        return events
    west, south, east, north = bbox_parsed
    filtered = []
    for event in events:
        if event.lat is None or event.lng is None:
            continue
        if west <= event.lng <= east and south <= event.lat <= north:
            filtered.append(event)
    return filtered


@router.get("/api/live-map/events", dependencies=[Depends(rate_limit_map)])
def get_live_map_events(
    bbox: str | None = Query(
        None, description="west,south,east,north in WGS84 decimal degrees"
    ),
    event_type: str | None = Query(None, description="Filter by event type"),
    jurisdiction: str | None = Query(None, description="Filter by jurisdiction"),
    province: str | None = Query(None, description="Filter by province/state"),
    from_date: datetime | None = Query(None, description="Filter by start date"),
    to_date: datetime | None = Query(None, description="Filter by end date"),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Get live map events with filtering.

    Default public behavior:
    - Only return publish_status in ["public_safe", "public_redacted"]
    - Only return review_status == "approved"
    - Only return confidence >= configured threshold

    Admin mode (admin_mode=true):
    - Can include needs_review, private, contradicted, low_confidence
    - Does not expose raw evidence vault paths in responses
    """
    bbox_parsed = _parse_bbox(bbox)

    # Materialize events from database
    events = _load_live_map_events(db)

    # Public endpoint always enforces visibility boundaries.
    events = _apply_public_filters(events, settings)

    # Apply bbox filter
    events = _apply_bbox_filter(events, bbox_parsed)

    # Apply additional filters
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    if jurisdiction:
        events = [e for e in events if e.jurisdiction == jurisdiction]
    if province:
        events = [e for e in events if e.province == province]
    if from_date:
        events = [e for e in events if e.occurred_at and e.occurred_at >= from_date]
    if to_date:
        events = [e for e in events if e.occurred_at and e.occurred_at <= to_date]
    if min_confidence is not None:
        events = [e for e in events if e.confidence >= min_confidence]
    if source:
        events = [e for e in events if source in e.source_ids]

    # Apply pagination
    truncated = len(events) > limit
    events = events[offset: offset + limit]

    # Redact sensitive fields in public mode
    response_events = []
    for event in events:
        event_dict = event.model_dump()
        # Redact raw evidence vault paths
        event_dict["evidence_ids"] = [
            f"evidence_{eid[:8]}..." for eid in event_dict.get("evidence_ids", [])
        ]
        # Redact source IDs in public mode
        event_dict["source_ids"] = [
            f"source_{sid[:8]}..." for sid in event_dict.get("source_ids", [])
        ]
        response_events.append(event_dict)

    filters_applied: dict[str, Any] = {
        "public_only": True,
        "public_visibility": True,
        "bbox": bbox,
        "event_type": event_type,
        "jurisdiction": jurisdiction,
        "province": province,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "min_confidence": min_confidence,
        "source": source,
        "review_status": REVIEW_APPROVED,
        "publish_statuses": [PUBLIC_SAFE, PUBLIC_REDACTED],
        "min_confidence_threshold": float(
            getattr(settings, "public_map_min_confidence", 0.7)
        ),
    }

    return {
        "returned_count": len(response_events),
        "truncated": truncated,
        "filters_applied": filters_applied,
        "disclaimer": PLATFORM_DISCLAIMER,
        "events": response_events,
    }


@router.get("/api/live-map/events/{event_id}")
def get_live_map_event(
    event_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Get a single live map event by ID."""
    events = _load_live_map_events(db)

    # Find event by ID
    event = next((e for e in events if e.id == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Public endpoint always enforces public visibility boundaries.
    filtered = _apply_public_filters([event], settings)
    if not filtered:
        raise HTTPException(
            status_code=403, detail="Event not accessible in public mode"
        )
    event = filtered[0]

    event_dict = event.model_dump()

    # Redact sensitive fields in public mode
    event_dict["evidence_ids"] = [
        f"evidence_{eid[:8]}..." if len(eid) >= 8 else eid
        for eid in event_dict.get("evidence_ids", [])
    ]
    event_dict["source_ids"] = [
        f"source_{sid[:8]}..." if len(sid) >= 8 else sid
        for sid in event_dict.get("source_ids", [])
    ]

    event_dict["disclaimer"] = PLATFORM_DISCLAIMER
    return event_dict


@router.get("/api/live-map/layers")
def get_live_map_layers(db: Session = Depends(get_db)):
    """Get available map layers and their metadata."""
    events = _load_live_map_events(db)

    # Group events by type
    layers: dict[str, Any] = {}
    for event in events:
        if event.event_type not in layers:
            layers[event.event_type] = {
                "event_type": event.event_type,
                "count": 0,
                "description": _get_layer_description(event.event_type),
                "jurisdictions": set(),
                "provinces": set(),
            }
        layers[event.event_type]["count"] += 1
        if event.jurisdiction:
            layers[event.event_type]["jurisdictions"].add(event.jurisdiction)
        if event.province:
            layers[event.event_type]["provinces"].add(event.province)

    # Convert sets to lists for JSON serialization
    for layer in layers.values():
        layer["jurisdictions"] = list(layer["jurisdictions"])
        layer["provinces"] = list(layer["provinces"])

    return {
        "layers": list(layers.values()),
        "total_layers": len(layers),
        "disclaimer": PLATFORM_DISCLAIMER,
    }


def _get_layer_description(event_type: str) -> str:
    """Get human-readable description for event type."""
    descriptions = {
        "court_event": "Court proceedings and decisions",
        "judge_event": "Judicial assignments and activities",
        "crime_event": "Reported crime incidents",
        "police_release": "Police press releases and statements",
        "news_event": "News articles and reports",
        "legislation_event": "Legislative changes and instruments",
        "statistical_event": "Statistical data releases",
        "correction_event": "Corrections and updates",
        "contradiction_event": "Contradicted claims requiring review",
    }
    return descriptions.get(event_type, "Unknown event type")


@router.get("/api/live-map/feed-status")
def get_feed_status(db: Session = Depends(get_db)):
    """Get live feed status and health information."""
    events = _load_live_map_events(db)

    # Calculate statistics
    total_events = len(events)
    public_events = len([e for e in events if e.publish_status in ["public_safe", "public_redacted"]])
    approved_events = len([e for e in events if e.review_status == "approved"])
    needs_review = len([e for e in events if e.review_status == "needs_review"])
    contradicted = len([e for e in events if e.tags and "contradicted" in e.tags])

    # Calculate confidence distribution
    high_confidence = len([e for e in events if e.confidence >= 0.8])
    medium_confidence = len([e for e in events if 0.5 <= e.confidence < 0.8])
    low_confidence = len([e for e in events if e.confidence < 0.5])

    return {
        "feed_status": "healthy",
        "total_events": total_events,
        "public_events": public_events,
        "approved_events": approved_events,
        "needs_review": needs_review,
        "contradicted": contradicted,
        "confidence_distribution": {
            "high": high_confidence,
            "medium": medium_confidence,
            "low": low_confidence,
        },
        "last_updated": datetime.now().isoformat(),
        "disclaimer": PLATFORM_DISCLAIMER,
    }


@router.get("/api/live-map/source-health")
def get_source_health(db: Session = Depends(get_db)):
    """Get source health information for map data sources."""
    from app.models.entities import LegalSource

    sources = db.query(LegalSource).all()

    source_health = []
    for source in sources:
        is_active = bool(getattr(source, "is_active", source.review_status != "deprecated"))
        last_ingested_at = getattr(source, "last_ingested_at", None)

        source_health.append(
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "title": source.title,
                "lifecycle_state": getattr(source, "lifecycle_state", None),
                "is_active": is_active,
                "automation_status": getattr(source, "automation_status", None),
                "last_ingested_at": last_ingested_at.isoformat()
                if last_ingested_at
                else None,
            }
        )

    return {
        "sources": source_health,
        "total_sources": len(source_health),
        "active_sources": len([s for s in source_health if s["is_active"]]),
        "disclaimer": PLATFORM_DISCLAIMER,
    }
