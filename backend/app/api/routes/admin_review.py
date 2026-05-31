from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin import (
    require_admin_review,
)
from app.audit.append_log import append_audit_entry
from app.auth.actor import AdminActor
from app.core.rate_limit import rate_limit_admin
from app.db.session import get_db
from app.security.import_authority import require_admin_actor, require_ai_review_actor
from app.models.entities import (
    CanonicalEntity,
    CrimeIncident,
    Event,
    EvidenceReview,
    LegalInstrument,
    LegalSource,
    MemoryClaim,
    MemoryContradiction,
    ReviewActionLog,
    ReviewItem,
)
from app.policies.publication_policy import (
    PUBLIC_REVIEW_STATUSES,
    REVIEW_STATUSES,
    can_publish_entity,
    entity_public_visibility,
    public_status_for_decision,
    set_entity_public_visibility,
)
from app.serializers.public import (
    entity_by_type,
    event_options,
)

router = APIRouter()


def _status_from_decision(entity, payload: dict) -> str:
    decision = str(
        payload.get("decision")
        or payload.get("action")
        or payload.get("review_status")
        or ""
    ).strip()
    requested = payload.get("approved_status") or payload.get("public_status")
    status = public_status_for_decision(
        "crime_incident" if isinstance(entity, CrimeIncident)
        else "legal_instrument" if isinstance(entity, LegalInstrument)
        else "source" if isinstance(entity, LegalSource)
        else "event",
        decision,
        requested_status=str(requested).strip() if requested else None,
    )
    if status in REVIEW_STATUSES:
        return status
    raise HTTPException(status_code=422, detail="Unsupported review decision")


def _serialize_review_item(db: Session, entity_type: str, entity) -> dict:
    title = (
        getattr(entity, "title", None)
        or getattr(entity, "incident_type", None)
        or getattr(entity, "source_id", None)
    )
    source_type = (
        getattr(entity, "source_type", None)
        or getattr(entity, "source_quality", None)
        or getattr(entity, "incident_category", None)
    )
    created_at = getattr(entity, "created_at", None)
    last_seen_at = (
        getattr(entity, "last_seen_at", None)
        or getattr(entity, "data_last_seen_at", None)
        or getattr(entity, "updated_at", None)
    )
    source_key = getattr(entity, "source_key", None)
    if source_key is None and getattr(entity, "source", None) is not None:
        source_key = getattr(entity.source, "source_key", None)

    policy_block_reasons: list[str] = []
    decision = can_publish_entity(db, entity_type, entity)
    if not decision.allowed:
        policy_block_reasons = decision.reasons

    return {
        "id": entity.id,
        "entity_type": entity_type,
        "entity_id": (
            getattr(entity, "event_id", None)
            if isinstance(entity, Event)
            else entity.id
        ),
        "database_id": entity.id,
        "title": title,
        "source_type": source_type,
        "source_id": getattr(entity, "source_id", None),
        "source_key": source_key,
        "jurisdiction": getattr(entity, "jurisdiction", None),
        "review_status": entity.review_status,
        "public_visibility": entity_public_visibility(entity),
        "raw_snapshot_id": getattr(entity, "raw_snapshot_id", None),
        "parser_version": getattr(entity, "parser_version", None),
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "created_at": created_at.isoformat() if created_at else None,
        "reviewed_by": getattr(entity, "reviewed_by", None),
        "reviewed_at": (
            getattr(entity, "reviewed_at").isoformat()
            if getattr(entity, "reviewed_at", None)
            else None
        ),
        "review_notes": getattr(entity, "review_notes", None),
        "correction_note": getattr(entity, "correction_note", None),
        "dispute_note": getattr(entity, "dispute_note", None),
        "policy_block_reasons": policy_block_reasons,
    }


def _query_count(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _review_statements(
    entity_type: str, review_status: str | None, source_type: str | None
):
    if entity_type == "event":
        data_stmt = select(Event).options(*event_options()).order_by(Event.id)
        count_stmt = select(Event.id)
        if review_status:
            data_stmt = data_stmt.where(Event.review_status == review_status)
            count_stmt = count_stmt.where(Event.review_status == review_status)
        if source_type:
            data_stmt = data_stmt.where(Event.source_quality == source_type)
            count_stmt = count_stmt.where(Event.source_quality == source_type)
        return data_stmt, count_stmt
    if entity_type == "crime_incident":
        data_stmt = select(CrimeIncident).order_by(CrimeIncident.id)
        count_stmt = select(CrimeIncident.id)
        if review_status:
            data_stmt = data_stmt.where(CrimeIncident.review_status == review_status)
            count_stmt = count_stmt.where(CrimeIncident.review_status == review_status)
        if source_type:
            data_stmt = data_stmt.where(CrimeIncident.incident_category == source_type)
            count_stmt = count_stmt.where(
                CrimeIncident.incident_category == source_type
            )
        return data_stmt, count_stmt
    if entity_type == "source":
        data_stmt = select(LegalSource).order_by(LegalSource.id)
        count_stmt = select(LegalSource.id)
        if review_status:
            data_stmt = data_stmt.where(LegalSource.review_status == review_status)
            count_stmt = count_stmt.where(LegalSource.review_status == review_status)
        if source_type:
            data_stmt = data_stmt.where(LegalSource.source_type == source_type)
            count_stmt = count_stmt.where(LegalSource.source_type == source_type)
        return data_stmt, count_stmt
    if entity_type == "legal_instrument":
        data_stmt = select(LegalInstrument).order_by(LegalInstrument.id)
        count_stmt = select(LegalInstrument.id)
        if review_status:
            data_stmt = data_stmt.where(LegalInstrument.review_status == review_status)
            count_stmt = count_stmt.where(LegalInstrument.review_status == review_status)
        return data_stmt, count_stmt
    raise HTTPException(status_code=404, detail="Unsupported entity type")


@router.get(
    "/api/admin/review-queue",
    dependencies=[Depends(require_admin_review), Depends(rate_limit_admin)],
)
def admin_review_queue(
    entity_type: str | None = None,
    review_status: str | None = None,
    source_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    requested_types = (
        [entity_type] if entity_type else ["event", "crime_incident", "source", "legal_instrument"]
    )
    total_count = 0
    items: list[dict] = []
    remaining_offset = offset
    remaining_limit = limit

    for current_type in requested_types:
        data_stmt, count_stmt = _review_statements(
            current_type, review_status, source_type
        )
        current_count = _query_count(db, count_stmt)
        total_count += current_count
        if remaining_limit <= 0:
            continue
        if remaining_offset >= current_count:
            remaining_offset -= current_count
            continue
        rows = (
            db.scalars(data_stmt.offset(remaining_offset).limit(remaining_limit))
            .unique()
            .all()
        )
        items.extend(_serialize_review_item(db, current_type, entity) for entity in rows)
        remaining_limit -= len(rows)
        remaining_offset = 0
    return {"items": items, "total_count": total_count}


@router.get(
    "/api/admin/review-history",
    dependencies=[Depends(require_admin_review), Depends(rate_limit_admin)],
)
def admin_review_history(
    entity_type: str | None = None,
    entity_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(EvidenceReview).order_by(
        EvidenceReview.reviewed_at.desc(), EvidenceReview.id.desc()
    )
    if entity_type:
        stmt = stmt.where(EvidenceReview.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(EvidenceReview.entity_id == entity_id)
    total_count = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset(offset).limit(limit)).all()
    items = [
        {
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "previous_status": row.previous_status,
            "new_status": row.new_status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "notes": row.notes,
            "public_visibility": row.public_visibility,
        }
        for row in rows
    ]
    return {"items": items, "total_count": total_count}


@router.post(
    "/api/admin/review-queue/{entity_type}/{entity_id}/decision",
    dependencies=[Depends(rate_limit_admin)],
)
async def admin_review_decision(
    entity_type: str,
    entity_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    entity = entity_by_type(db, entity_type, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Review entity not found")

    previous_status = entity.review_status
    new_status = _status_from_decision(entity, payload)
    if new_status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported review status")
    public_visibility = new_status in PUBLIC_REVIEW_STATUSES
    reviewer = str(payload.get("reviewed_by") or actor.actor_id)
    now = datetime.now(timezone.utc)

    entity.review_status = new_status
    if hasattr(entity, "reviewed_by"):
        entity.reviewed_by = reviewer
    if hasattr(entity, "reviewed_at"):
        entity.reviewed_at = now
    if hasattr(entity, "review_notes"):
        entity.review_notes = payload.get("notes")
    if new_status == "corrected" and hasattr(entity, "correction_note"):
        entity.correction_note = payload.get("correction_note") or payload.get("notes")
    if new_status == "disputed" and hasattr(entity, "dispute_note"):
        entity.dispute_note = payload.get("dispute_note") or payload.get("notes")
    if public_visibility:
        decision = can_publish_entity(db, entity_type, entity)
        if not decision.allowed:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Publication policy blocked this entity.",
                    "Evidence snapshot": (
                        "Evidence snapshot with content_hash"
                        " required before publishing entity."
                    ),
                    "reasons": decision.reasons,
                },
            )
    else:
        public_visibility = False
    set_entity_public_visibility(entity, public_visibility)

    db.add(
        EvidenceReview(
            entity_type=entity_type,
            entity_id=entity.id,
            previous_status=previous_status,
            new_status=new_status,
            reviewed_by=reviewer,
            reviewed_at=now,
            notes=payload.get("notes"),
            public_visibility=public_visibility,
        )
    )
    append_audit_entry(
        db,
        action="review.decision",
        entity_type=entity_type,
        entity_id=str(entity.id),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        actor_role=actor.role,
        actor_ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
        payload={
            "previous_status": previous_status,
            "new_status": new_status,
            "decision": payload.get("decision") or payload.get("action"),
            "notes": payload.get("notes"),
        },
    )
    # Write ReviewActionLog if there is a ReviewItem linked via source_snapshot_id.
    _snap_id = getattr(entity, "source_snapshot_id", None)
    if _snap_id is not None:
        _ri = db.scalar(
            select(ReviewItem).where(ReviewItem.source_snapshot_id == _snap_id)
        )
        if _ri is not None:
            db.add(
                ReviewActionLog(
                    review_item_id=_ri.id,
                    actor=reviewer,
                    action=new_status,
                    before_json={"review_status": previous_status},
                    after_json={
                        "review_status": new_status,
                        "is_public": public_visibility,
                    },
                )
            )
    db.commit()
    return _serialize_review_item(db, entity_type, entity)


@router.post(
    "/api/admin/legal-sources/{source_id}/retract",
    dependencies=[Depends(rate_limit_admin)],
)
def retract_legal_source(
    source_id: str,
    reason: str | None = Query(
        None, max_length=1000, description="Reason for retraction"
    ),
    request: Request = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_actor),
) -> dict:
    """Permanently retract a legal source from public visibility.

    Sets review_status to 'removed_from_public', clears public_visibility,
    and writes an EvidenceReview audit record. Requires admin/owner or
    source_admin role via JWT Bearer or shared admin token.
    """
    source = db.scalar(select(LegalSource).where(LegalSource.source_id == source_id))
    if not source:
        raise HTTPException(
            status_code=404, detail=f"Legal source '{source_id}' not found"
        )

    _RETRACTION_STATUS = "removed_from_public"
    previous_status = source.review_status
    now = datetime.now(timezone.utc)

    source.review_status = _RETRACTION_STATUS
    source.public_visibility = False
    source.reviewed_by = actor.actor_id
    source.reviewed_at = now
    if reason:
        source.review_notes = reason

    db.add(
        EvidenceReview(
            entity_type="source",
            entity_id=source.id,
            previous_status=previous_status,
            new_status=_RETRACTION_STATUS,
            reviewed_by=actor.actor_id,
            reviewed_at=now,
            notes=reason,
            public_visibility=False,
        )
    )
    append_audit_entry(
        db,
        action="review.retraction",
        entity_type="source",
        entity_id=str(source.id),
        actor_id=actor.actor_id,
        actor_type="admin",
        actor_role=actor.role,
        actor_ip=(request.client.host if request and request.client else None),
        user_agent=(request.headers.get("user-agent") if request else None),
        request_id=(request.headers.get("x-request-id") if request else None),
        payload={
            "previous_status": previous_status,
            "new_status": _RETRACTION_STATUS,
            "reason": reason,
        },
    )
    db.commit()
    return _serialize_review_item(db, "source", source)


@router.get(
    "/api/admin/contradictions",
    dependencies=[Depends(require_admin_review), Depends(rate_limit_admin)],
)
def list_open_contradictions(
    severity: str | None = Query(None, description="Filter by severity"),
    conflict_type: str | None = Query(None, description="Filter by conflict type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List open contradictions for reviewer dashboard."""
    stmt = select(MemoryContradiction).where(
        MemoryContradiction.status == "open"
    ).order_by(MemoryContradiction.detected_at.desc())

    if severity:
        stmt = stmt.where(MemoryContradiction.severity == severity)
    if conflict_type:
        stmt = stmt.where(MemoryContradiction.conflict_type == conflict_type)

    total_count = (
        db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    rows = db.scalars(stmt.offset(offset).limit(limit)).all()

    items = [
        {
            "id": row.id,
            "claim_a_id": row.claim_a_id,
            "claim_b_id": row.claim_b_id,
            "conflict_type": row.conflict_type,
            "severity": row.severity,
            "status": row.status,
            "detected_by": row.detected_by,
            "detected_at": row.detected_at.isoformat() if row.detected_at else None,
            "reviewer_id": row.reviewer_id,
            "resolution_note": row.resolution_note,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        }
        for row in rows
    ]
    return {"items": items, "total_count": total_count}


@router.get(
    "/api/admin/contradictions/by-claim/{claim_id}",
    dependencies=[Depends(require_admin_review), Depends(rate_limit_admin)],
)
def get_contradictions_by_claim(
    claim_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get contradictions for a specific claim with pagination."""
    query = (
        db.query(MemoryContradiction)
        .filter(
            (MemoryContradiction.claim_a_id == claim_id)
            | (MemoryContradiction.claim_b_id == claim_id)
        )
        .order_by(MemoryContradiction.detected_at.desc())
    )

    total_count = query.count()
    contradictions = query.offset(offset).limit(limit).all()

    items = [
        {
            "id": c.id,
            "claim_a_id": c.claim_a_id,
            "claim_b_id": c.claim_b_id,
            "conflict_type": c.conflict_type,
            "severity": c.severity,
            "status": c.status,
            "detected_by": c.detected_by,
            "detected_at": c.detected_at.isoformat() if c.detected_at else None,
            "reviewer_id": c.reviewer_id,
            "resolution_note": c.resolution_note,
            "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        }
        for c in contradictions
    ]
    return {"items": items, "total_count": total_count}


@router.get(
    "/api/admin/contradictions/by-entity/{entity_id}",
    dependencies=[Depends(require_admin_review), Depends(rate_limit_admin)],
)
def get_contradictions_by_entity(
    entity_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get contradictions for claims related to an entity with pagination."""
    # Get all claims for the entity
    claim_ids = (
        db.query(MemoryClaim.id)
        .filter(MemoryClaim.entity_id == entity_id)
        .all()
    )
    claim_ids = [c[0] for c in claim_ids]

    if not claim_ids:
        return {"items": [], "total_count": 0}

    # Get contradictions for those claims
    query = (
        db.query(MemoryContradiction)
        .filter(
            (MemoryContradiction.claim_a_id.in_(claim_ids))
            | (MemoryContradiction.claim_b_id.in_(claim_ids))
        )
        .order_by(MemoryContradiction.detected_at.desc())
    )

    total_count = query.count()
    contradictions = query.offset(offset).limit(limit).all()

    items = [
        {
            "id": c.id,
            "claim_a_id": c.claim_a_id,
            "claim_b_id": c.claim_b_id,
            "conflict_type": c.conflict_type,
            "severity": c.severity,
            "status": c.status,
            "detected_by": c.detected_by,
            "detected_at": c.detected_at.isoformat() if c.detected_at else None,
            "reviewer_id": c.reviewer_id,
            "resolution_note": c.resolution_note,
            "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        }
        for c in contradictions
    ]
    return {"items": items, "total_count": total_count}


@router.post(
    "/api/admin/contradictions/{contradiction_id}/resolve",
    dependencies=[Depends(rate_limit_admin)],
)
def resolve_contradiction(
    contradiction_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_actor),
):
    """Resolve a contradiction with reviewer action."""
    contradiction = db.query(MemoryContradiction).filter(
        MemoryContradiction.id == contradiction_id
    ).first()

    if not contradiction:
        raise HTTPException(
            status_code=404, detail=f"Contradiction {contradiction_id} not found"
        )

    new_status = payload.get("status", "resolved")
    if new_status not in ["resolved", "false_positive", "ignored"]:
        raise HTTPException(
            status_code=422, detail="Invalid status. Must be resolved, false_positive, or ignored"
        )

    previous_status = contradiction.status
    now = datetime.now(timezone.utc)

    contradiction.status = new_status
    contradiction.reviewer_id = actor.actor_id
    contradiction.resolution_note = payload.get("resolution_note")
    # Only set resolved_at for actual resolutions, not ignored
    if new_status != "ignored":
        contradiction.resolved_at = now

    # Decrement contradiction counts on both claims
    claim_a = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_a_id
    ).first()
    claim_b = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_b_id
    ).first()

    if claim_a and claim_a.contradiction_count > 0:
        claim_a.contradiction_count -= 1
    if claim_b and claim_b.contradiction_count > 0:
        claim_b.contradiction_count -= 1

    append_audit_entry(
        db,
        action="contradiction.resolution",
        entity_type="memory_contradiction",
        entity_id=str(contradiction.id),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        actor_role=actor.role,
        actor_ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
        payload={
            "previous_status": previous_status,
            "new_status": new_status,
            "resolution_note": payload.get("resolution_note"),
        },
    )

    db.commit()

    return {
        "id": contradiction.id,
        "claim_a_id": contradiction.claim_a_id,
        "claim_b_id": contradiction.claim_b_id,
        "conflict_type": contradiction.conflict_type,
        "severity": contradiction.severity,
        "status": contradiction.status,
        "detected_by": contradiction.detected_by,
        "detected_at": contradiction.detected_at.isoformat() if contradiction.detected_at else None,
        "reviewer_id": contradiction.reviewer_id,
        "resolution_note": contradiction.resolution_note,
        "resolved_at": contradiction.resolved_at.isoformat() if contradiction.resolved_at else None,
    }

