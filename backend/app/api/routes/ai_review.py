from datetime import date, datetime, timezone
from uuid import uuid4

from app.ai.pipeline import run_ai_pipeline
from app.auth.actor import AdminActor
from app.auth.admin import (
    enforce_jwt_mutation_authority,
    log_mutation,
    require_admin_review,
)
from app.db.session import get_db
from app.models.entities import (
    Case,
    Court,
    Event,
    EventSource,
    Judge,
    LegalSource,
    Location,
    ReviewActionLog,
    ReviewItem,
)
from app.policies.state_model import (
    ReviewQueueDecision,
    normalize_review_queue_decision,
)
from app.security.import_authority import require_ai_review_actor
from app.services.constants import AI_REVIEW_ITEM_STATUSES, ALLOWED_EVENT_TYPES
from app.services.linker import url_hash
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter()


def _serialize_ai_review_item(item: ReviewItem) -> dict:
    payload = item.suggested_payload_json or {}
    return {
        "id": item.id,
        "record_type": item.record_type,
        "raw_source_id": item.raw_source_id,
        "suggested_payload_json": payload,
        "source_url": item.source_url,
        "source_quality": item.source_quality,
        "confidence": item.confidence,
        "privacy_status": item.privacy_status,
        "publish_recommendation": item.publish_recommendation,
        "status": item.status,
        "reviewer_id": item.reviewer_id,
        "reviewer_notes": item.reviewer_notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "source_quote": payload.get("source_quote"),
        "neutral_summary": payload.get("neutral_summary"),
    }


def _transition_ai_review_item(
    db: Session,
    item_id: int,
    status: str,
    payload: dict | None = None,
    commit: bool = True,
) -> dict:
    if status not in AI_REVIEW_ITEM_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported AI review status")
    item = db.get(ReviewItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    payload = payload or {}
    before = _serialize_ai_review_item(item)
    item.status = status
    item.reviewer_id = str(
        payload.get("reviewer_id") or payload.get("actor") or "admin"
    )
    item.reviewer_notes = payload.get("notes")
    item.reviewed_at = datetime.now(timezone.utc)
    db.add(
        ReviewActionLog(
            review_item_id=item.id,
            actor=item.reviewer_id,
            action=status,
            before_json=before,
            after_json={"status": status, "reviewer_notes": item.reviewer_notes},
        )
    )
    if commit:
        db.commit()
    return _serialize_ai_review_item(item)


def _publish_review_item_as_event(db: Session, item: ReviewItem) -> Event:
    payload = item.suggested_payload_json or {}
    required = ["court_id", "case_id", "primary_location_id"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Review item missing required event fields: {', '.join(missing)}",
        )

    court = db.get(Court, int(payload["court_id"]))
    case = db.get(Case, int(payload["case_id"]))
    location = db.get(Location, int(payload["primary_location_id"]))
    judge_id = payload.get("judge_id")
    judge = db.get(Judge, int(judge_id)) if judge_id else None
    if not court or not case or not location or (judge_id and not judge):
        raise HTTPException(
            status_code=422,
            detail="Review item references missing court, case, location, or judge",
        )

    event_type = _event_type_for_ai_payload(str(payload.get("event_type") or "unknown"))
    event = Event(
        event_id=f"EVT-AI-{uuid4().hex[:12].upper()}",
        court_id=court.id,
        judge_id=judge.id if judge else None,
        case_id=case.id,
        primary_location_id=location.id,
        event_type=event_type,
        event_subtype="ai_review_draft",
        decision_result=event_type,
        decision_date=_date_from_payload(payload.get("decision_date")),
        posted_date=None,
        title=str(payload.get("title") or "AI reviewed legal event"),
        summary=str(
            payload.get("summary")
            or payload.get("neutral_summary")
            or "AI-assisted reviewed event pending human evidence review."
        ),
        repeat_offender_indicator=bool(payload.get("repeat_offender_indicator")),
        verified_flag=False,
        source_quality=item.source_quality,
        last_verified_at=None,
        classifier_metadata={
            "source_excerpt": payload.get("source_quote"),
            "verification_status": (
                "indicator_only"
                if payload.get("repeat_offender_indicator")
                else "not_indicated"
            ),
            "repeat_offender_indicators": payload.get("repeat_offender_indicators")
            or [],
            "ai_review_item_id": item.id,
        },
        review_status="pending_review",
        public_visibility=False,
    )
    db.add(event)
    db.flush()
    source = _get_or_create_ai_source(db, item)
    if source:
        db.add(EventSource(event_id=event.id, source_id=source.id))
    return event


def _get_or_create_ai_source(db: Session, item: ReviewItem) -> LegalSource | None:
    if not item.source_url:
        return None
    hashed = url_hash(item.source_url)
    source = db.scalar(select(LegalSource).where(LegalSource.url_hash == hashed))
    if source:
        return source
    source = LegalSource(
        source_id=f"SRC-AI-{uuid4().hex[:12].upper()}",
        source_type=item.source_quality,
        title=f"AI review source {item.id}",
        url=item.source_url,
        api_url=None,
        url_hash=hashed,
        source_quality=item.source_quality,
        verified_flag=False,
        retrieved_at=datetime.now(timezone.utc),
        review_status="pending_review",
        public_visibility=False,
    )
    db.add(source)
    db.flush()
    return source


def _event_type_for_ai_payload(value: str) -> str:
    mapping = {
        "bail_decision": "bond_modification",
        "release_decision": "release_order",
        "appeal_decision": "appeal_affirmance",
        "court_order": "published_opinion",
        "unknown": "news_coverage",
    }
    event_type = mapping.get(value, value)
    if event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=422, detail="Review item event type is unsupported"
        )
    return event_type


def _date_from_payload(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@router.get("/api/admin/review/items", dependencies=[Depends(require_admin_review)])
def ai_review_items(
    status: str | None = None,
    record_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(ReviewItem).order_by(
        ReviewItem.created_at.desc(), ReviewItem.id.desc()
    )
    count_stmt = select(ReviewItem.id)
    if status:
        stmt = stmt.where(ReviewItem.status == status)
        count_stmt = count_stmt.where(ReviewItem.status == status)
    if record_type:
        stmt = stmt.where(ReviewItem.record_type == record_type)
        count_stmt = count_stmt.where(ReviewItem.record_type == record_type)
    total = db.scalar(select(func.count()).select_from(count_stmt.subquery())) or 0
    items = db.scalars(stmt.offset(offset).limit(limit)).all()
    return {
        "items": [_serialize_ai_review_item(item) for item in items],
        "total_count": total,
    }


@router.get(
    "/api/admin/review/items/{item_id}", dependencies=[Depends(require_admin_review)]
)
def ai_review_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ReviewItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return _serialize_ai_review_item(item)


@router.post("/api/admin/review/items/{item_id}/approve")
def approve_ai_review_item(
    item_id: int,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    enforce_jwt_mutation_authority(actor)
    result = _transition_ai_review_item(db, item_id, "approved", payload, commit=False)
    try:
        log_mutation(
            action="ai_review_item.approve",
            entity_type="review_item",
            entity_id=str(item_id),
            actor=actor,
            request=request,
            payload={"status": "approved"},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return result


@router.post("/api/admin/review/items/{item_id}/reject")
def reject_ai_review_item(
    item_id: int,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    enforce_jwt_mutation_authority(actor)
    result = _transition_ai_review_item(db, item_id, "rejected", payload, commit=False)
    try:
        log_mutation(
            action="ai_review_item.reject",
            entity_type="review_item",
            entity_id=str(item_id),
            actor=actor,
            request=request,
            payload={"status": "rejected"},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return result


@router.post("/api/admin/review/items/{item_id}/needs-more-sources")
def needs_more_sources_ai_review_item(
    item_id: int,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    enforce_jwt_mutation_authority(actor)
    result = _transition_ai_review_item(
        db, item_id, "needs_more_sources", payload, commit=False
    )
    try:
        log_mutation(
            action="ai_review_item.needs_more_sources",
            entity_type="review_item",
            entity_id=str(item_id),
            actor=actor,
            request=request,
            payload={"status": "needs_more_sources"},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return result


@router.post("/api/admin/review/items/{item_id}/block")
def block_ai_review_item(
    item_id: int,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    enforce_jwt_mutation_authority(actor)
    result = _transition_ai_review_item(db, item_id, "blocked", payload, commit=False)
    try:
        log_mutation(
            action="ai_review_item.block",
            entity_type="review_item",
            entity_id=str(item_id),
            actor=actor,
            request=request,
            payload={"status": "blocked"},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return result


@router.post("/api/admin/review/items/{item_id}/publish")
def publish_ai_review_item(
    item_id: int,
    request: Request,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    """Promote an approved ReviewItem to an Event draft.

    Despite the route name, this does NOT make anything publicly visible.
    The created Event has public_visibility=False and review_status='pending_review',
    making it an internal draft that requires a separate visibility promotion step
    before it appears in public-facing queries.
    """
    enforce_jwt_mutation_authority(actor)
    item = db.get(ReviewItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.status == "blocked" or item.publish_recommendation == "block":
        raise HTTPException(
            status_code=422, detail="Blocked review items cannot publish"
        )
    if item.privacy_status == "privacy_risk":
        raise HTTPException(
            status_code=422,
            detail="Privacy-risk review items require separate legal review before publishing",
        )
    if normalize_review_queue_decision(item.status) != ReviewQueueDecision.APPROVED:
        raise HTTPException(
            status_code=422, detail="Review item must be approved before publishing"
        )
    if item.record_type != "legal_event":
        raise HTTPException(
            status_code=422,
            detail="Only legal event review items can publish in this prototype",
        )

    event = _publish_review_item_as_event(db, item)
    _transition_ai_review_item(db, item_id, "published", payload, commit=False)
    try:
        log_mutation(
            action="ai_review_item.publish",
            entity_type="review_item",
            entity_id=str(item_id),
            actor=actor,
            request=request,
            payload={"status": "published", "event_id": event.event_id},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return {"review_item": _serialize_ai_review_item(item), "event_id": event.event_id}


@router.post("/api/admin/ai/process-source/{source_id}")
def process_source_with_ai(
    source_id: str,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    enforce_jwt_mutation_authority(actor)
    source = db.scalar(select(LegalSource).where(LegalSource.source_id == source_id))
    if not source and source_id.isdigit():
        source = db.get(LegalSource, int(source_id))
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    raw = {
        "record_type": (
            "crime_incident"
            if source.source_type == "official_police_open_data"
            else "legal_event"
        ),
        "source_url": source.url,
        "source_quality": source.source_quality,
        "title": source.title,
        "text": f"{source.title}. Source quality: {source.source_quality}.",
    }
    item = run_ai_pipeline(db, raw, raw_source_id=source.id)
    try:
        log_mutation(
            action="ai_process_source",
            entity_type="review_item",
            entity_id=str(item.id),
            actor=actor,
            payload={"source_id": source_id},
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    db.refresh(item)
    return {"review_item_id": item.id}
