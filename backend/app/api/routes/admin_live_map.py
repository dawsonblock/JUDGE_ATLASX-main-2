"""Admin live map API endpoints.

Admin routes are separated from public live-map endpoints and require
JWT-authenticated reviewer-or-higher access.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.audit.append_log import append_audit_entry
from app.auth.actor import AdminActor
from app.auth.admin import require_reviewer
from app.core.rate_limit import rate_limit_admin
from app.db.session import get_db
from app.schemas.geo_legal_event import GeoLegalEvent
from app.api.routes.live_map import (
    PLATFORM_DISCLAIMER,
    _apply_bbox_filter,
    _load_live_map_events,
    _parse_bbox,
)

router = APIRouter()


def _require_admin_live_map_actor(
    actor: AdminActor = Depends(require_reviewer),
) -> AdminActor:
    if actor.auth_method != "jwt":
        raise HTTPException(
            status_code=403,
            detail="JWT authentication is required for admin live-map access",
        )
    return actor


def _audit_live_map_access(
    db: Session,
    actor: AdminActor,
    action: str,
    payload: dict[str, Any],
    request_id: str | None,
    user_agent: str | None,
) -> None:
    append_audit_entry(
        db,
        action=action,
        entity_type="live_map",
        entity_id=None,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        actor_role=actor.role,
        actor_auth_method=actor.auth_method,
        request_id=request_id,
        user_agent=user_agent,
        payload=payload,
    )
    db.commit()


@router.get(
    "/api/admin/live-map/events",
    dependencies=[Depends(rate_limit_admin)],
)
def admin_live_map_events(
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
    review_status: str | None = Query(None, description="Filter by review status"),
    publish_status: str | None = Query(None, description="Filter by publish status"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(_require_admin_live_map_actor),
):
    bbox_parsed = _parse_bbox(bbox)
    events: list[GeoLegalEvent] = _load_live_map_events(db)
    events = _apply_bbox_filter(events, bbox_parsed)

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
    if review_status:
        events = [e for e in events if e.review_status == review_status]
    if publish_status:
        events = [e for e in events if e.publish_status == publish_status]
    if source:
        events = [e for e in events if source in e.source_ids]

    truncated = len(events) > limit
    events = events[offset: offset + limit]

    _audit_live_map_access(
        db,
        actor,
        action="admin_live_map_events_read",
        payload={
            "returned_count": len(events),
            "limit": limit,
            "offset": offset,
            "filters": {
                "bbox": bbox,
                "event_type": event_type,
                "jurisdiction": jurisdiction,
                "province": province,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "min_confidence": min_confidence,
                "review_status": review_status,
                "publish_status": publish_status,
                "source": source,
            },
        },
        request_id=request_id,
        user_agent=user_agent,
    )

    return {
        "returned_count": len(events),
        "truncated": truncated,
        "filters_applied": {
            "admin_mode": True,
            "bbox": bbox,
            "event_type": event_type,
            "jurisdiction": jurisdiction,
            "province": province,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "min_confidence": min_confidence,
            "review_status": review_status,
            "publish_status": publish_status,
            "source": source,
        },
        "disclaimer": PLATFORM_DISCLAIMER,
        "events": [event.model_dump() for event in events],
    }


@router.get(
    "/api/admin/live-map/events/{event_id}",
    dependencies=[Depends(rate_limit_admin)],
)
def admin_live_map_event(
    event_id: str,
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(_require_admin_live_map_actor),
):
    events: list[GeoLegalEvent] = _load_live_map_events(db)
    event = next((e for e in events if e.id == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _audit_live_map_access(
        db,
        actor,
        action="admin_live_map_event_read",
        payload={"event_id": event_id},
        request_id=request_id,
        user_agent=user_agent,
    )

    event_dict = event.model_dump()
    event_dict["disclaimer"] = PLATFORM_DISCLAIMER
    return event_dict
