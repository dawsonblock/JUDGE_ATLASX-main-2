"""Rule-based validation check API routes.

GET  /api/admin/correctness/checks          — list checks (admin)
GET  /api/admin/correctness/checks/{id}     — single check (admin)
POST /api/admin/correctness/run/incident/{id} — run check on CrimeIncident
POST /api/admin/correctness/run/event/{id}  — run check on court Event

Public map endpoint:
GET  /api/map/records/{record_type}/{id}/quality — quality label for a dot
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin import (
    log_mutation,
    require_admin_review,
)
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.models.entities import (
    AICorrectnessCheck,
    CrimeIncident,
    Event,
)
from app.services.ai_correctness import (
    check_court_event,
    check_crime_incident,
    is_safe_to_show,
)
from app.security.import_authority import require_ai_review_actor

router = APIRouter()


def _serialize(chk: AICorrectnessCheck) -> dict:
    return {
        "id": chk.id,
        "record_type": chk.record_type,
        "record_id": chk.record_id,
        "model_name": chk.model_name,
        "prompt_version": chk.prompt_version,
        "event_type_supported": chk.event_type_supported,
        "date_supported": chk.date_supported,
        "location_supported": chk.location_supported,
        "status_supported": chk.status_supported,
        "source_supports_claim": chk.source_supports_claim,
        "duplicate_candidate": chk.duplicate_candidate,
        "possible_duplicate_ids": chk.possible_duplicate_ids or [],
        "privacy_risk": chk.privacy_risk,
        "map_quality": chk.map_quality,
        "reason": chk.reason,
        "safe_to_show": is_safe_to_show(chk),
        "checked_at": chk.checked_at.isoformat(),
        "created_at": chk.created_at.isoformat() if chk.created_at else None,
        "findings": [
            {
                "finding_type": f.finding_type,
                "field_name": f.field_name,
                "expected": f.expected,
                "found": f.found,
                "severity": f.severity,
                "note": f.note,
            }
            for f in (chk.findings or [])
        ],
    }


@router.get(
    "/api/admin/correctness/checks",
    dependencies=[Depends(require_admin_review)],
)
def list_checks(
    map_quality: str | None = None,
    privacy_risk: str | None = None,
    record_type: str | None = None,
    duplicate_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(AICorrectnessCheck).order_by(
        AICorrectnessCheck.id.desc()
    )
    if map_quality:
        stmt = stmt.where(AICorrectnessCheck.map_quality == map_quality)
    if privacy_risk:
        stmt = stmt.where(AICorrectnessCheck.privacy_risk == privacy_risk)
    if record_type:
        stmt = stmt.where(AICorrectnessCheck.record_type == record_type)
    if duplicate_only:
        stmt = stmt.where(AICorrectnessCheck.duplicate_candidate.is_(True))
    items = db.scalars(stmt.offset(offset).limit(limit)).all()
    return {"checks": [_serialize(c) for c in items], "count": len(items)}


@router.get(
    "/api/admin/correctness/checks/{check_id}",
    dependencies=[Depends(require_admin_review)],
)
def get_check(check_id: int, db: Session = Depends(get_db)):
    chk = db.get(AICorrectnessCheck, check_id)
    if not chk:
        raise HTTPException(status_code=404, detail="Check not found")
    return _serialize(chk)


@router.post(
    "/api/admin/correctness/run/incident/{incident_id}",
)
def run_incident_check(
    incident_id: int,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    incident = db.get(CrimeIncident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="CrimeIncident not found")
    chk = check_crime_incident(db, incident)
    try:
        log_mutation(
            action="ai_correctness.run_incident",
            entity_type="crime_incident",
            entity_id=str(incident_id),
            payload={"check_id": chk.id, "status": chk.status},
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Audit logging failed; mutation aborted",
        )
    return _serialize(chk)


@router.post(
    "/api/admin/correctness/run/event/{event_id}",
)
def run_event_check(
    event_id: int,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    chk = check_court_event(db, event)
    try:
        log_mutation(
            action="ai_correctness.run_event",
            entity_type="event",
            entity_id=str(event_id),
            payload={"check_id": chk.id, "status": chk.status},
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Audit logging failed; mutation aborted",
        )
    return _serialize(chk)


@router.post(
    "/api/admin/ai/verify-source/{record_type}/{record_id}",
)
def verify_source_endpoint(
    record_type: str,
    record_id: int,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_ai_review_actor),
):
    """Trigger source-grounded verification for a court Event or CrimeIncident.

    Fetches the primary source URL, extracts text, and uses a local Ollama
    model to produce field-level support findings.  Stores findings in the
    most recent AICorrectnessCheck.result_json under key 'source_verification'.

    No guilt scores, danger scores, judge scores, or defendant scores are
    produced or stored.

    Returns 503 if Ollama is disabled or unreachable.
    Returns 404 if the record or its existing correctness check is not found.
    """
    from app.services.source_verifier import verify_source

    # Locate the record and pull primary source URL + claimed fields
    if record_type == "event":
        record = db.get(Event, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Event not found")
        source_url = next(
            (link.source.url for link in (record.source_links or []) if link.source and link.source.url),
            None,
        )
        claimed_fields = {
            "event_type": record.event_type or "",
            "decision_date": str(record.decision_date) if record.decision_date else "",
            "decision_result": record.decision_result or "",
            "summary": (record.summary or "")[:500],
        }
    elif record_type == "crime_incident":
        from app.models.entities import CrimeIncident
        record = db.get(CrimeIncident, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="CrimeIncident not found")
        source_url = record.source_url
        claimed_fields = {
            "incident_type": record.incident_type or "",
            "location": record.city or "",
            "status": record.verification_status or "",
        }
    else:
        raise HTTPException(status_code=422, detail="record_type must be 'event' or 'crime_incident'")

    if not source_url:
        raise HTTPException(status_code=422, detail="Record has no source URL to verify against")

    sv_result = verify_source(record_type, record_id, source_url, claimed_fields)

    if sv_result.status == "disabled":
        raise HTTPException(
            status_code=503,
            detail="Source verifier is disabled. Set JTA_OLLAMA_ENABLED=true to enable.",
        )

    # Store findings into the latest correctness check's result_json
    chk = db.scalars(
        select(AICorrectnessCheck)
        .where(
            AICorrectnessCheck.record_type == record_type,
            AICorrectnessCheck.record_id == record_id,
        )
        .order_by(AICorrectnessCheck.id.desc())
    ).first()
    if chk:
        existing = dict(chk.result_json or {})
        existing["source_verification"] = {
            "status": sv_result.status,
            "model": sv_result.model_name,
            "source_url": sv_result.source_url,
            "findings": sv_result.findings,
            "error": sv_result.error,
        }
        chk.result_json = existing
        try:
            log_mutation(
                action="ai_correctness.verify_source",
                entity_type=record_type,
                entity_id=str(record_id),
                payload={"check_id": chk.id, "status": sv_result.status},
                actor=actor,
                db=db,
                fail_closed=True,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Audit logging failed; mutation aborted",
            )

    return {
        "record_type": record_type,
        "record_id": record_id,
        "status": sv_result.status,
        "model": sv_result.model_name,
        "source_url": sv_result.source_url,
        "findings": sv_result.findings,
        "error": sv_result.error,
    }


@router.get("/api/map/records/{record_type}/{record_id}/quality")
def public_record_quality(
    record_type: str,
    record_id: int,
    db: Session = Depends(get_db),
):
    """Return latest quality label for a public map dot.

    Only returns the label when the record is safe to show.
    Does NOT expose guilt score, judge score, or danger score.
    """
    stmt = (
        select(AICorrectnessCheck)
        .where(
            AICorrectnessCheck.record_type == record_type,
            AICorrectnessCheck.record_id == record_id,
        )
        .order_by(AICorrectnessCheck.id.desc())
    )
    chk = db.scalars(stmt).first()
    if not chk:
        return {"map_quality": "unverified", "safe_to_show": False}
    return {
        "map_quality": chk.map_quality,
        "privacy_risk": chk.privacy_risk,
        "safe_to_show": is_safe_to_show(chk),
        "checked_at": chk.checked_at.isoformat(),
        "reason": chk.reason,
    }
