"""Admin memory layer management API.

Provides endpoints to inspect and trigger the Fluid Memory State Engine.
All endpoints require admin token authentication.

Does NOT import from map_record, graph edge, or public event tables.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.admin import (
    enforce_jwt_mutation_authority,
    log_mutation,
    require_admin_token,
)
from app.auth.actor import AdminActor
from app.db.session import SessionLocal, get_db
from app.memory.invalidation import invalidate_claim
from app.memory.rebuild import run_rebuild
from app.memory.retrieval import get_active_claims, get_entity_state, list_claims
from app.models.entities import MemoryRebuildRun
from app.security.import_authority import require_admin_actor

router = APIRouter(prefix="/api/admin/memory", tags=["admin_memory"])


class RebuildRequest(BaseModel):
    scope: str = "full"
    entity_id: int | None = None


@router.get("/status")
def get_status(
    _: AdminActor = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict:
    """Return stats on the most recent rebuild run."""
    latest = db.query(MemoryRebuildRun).order_by(MemoryRebuildRun.id.desc()).first()
    if latest is None:
        return {"status": "no_runs", "run": None}
    return {
        "status": latest.status,
        "run": {
            "id": latest.id,
            "rebuild_scope": latest.rebuild_scope,
            "scope_entity_id": latest.scope_entity_id,
            "entities_processed": latest.entities_processed,
            "claims_created": latest.claims_created,
            "claims_invalidated": latest.claims_invalidated,
            "states_updated": latest.states_updated,
            "started_at": latest.started_at,
            "finished_at": latest.finished_at,
            "error_message": latest.error_message,
        },
    }


@router.post("/rebuild", status_code=202)
def trigger_rebuild(
    body: RebuildRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    actor: AdminActor = Depends(require_admin_actor),
    db: Session = Depends(get_db),
) -> dict:
    """Enqueue an async memory rebuild run.

    Returns 202 Accepted immediately and runs the rebuild in a background task
    so that the HTTP connection is not held open during long rebuilds.
    Poll GET /rebuild/status to check progress.
    """
    enforce_jwt_mutation_authority(actor)
    if body.scope not in {"full", "entity"}:
        raise HTTPException(status_code=400, detail=f"Unknown scope: {body.scope!r}")
    if body.scope == "entity" and body.entity_id is None:
        raise HTTPException(
            status_code=400, detail="entity_id required for scope='entity'"
        )

    def _run_in_background() -> None:
        with SessionLocal() as bg_db:
            try:
                run_rebuild(scope=body.scope, db=bg_db, entity_id=body.entity_id)
                bg_db.commit()
            except Exception:
                bg_db.rollback()
                raise

    background_tasks.add_task(_run_in_background)
    try:
        log_mutation(
            action="memory.rebuild.enqueue",
            entity_type="memory_rebuild",
            entity_id=None,
            payload={"scope": body.scope, "entity_id": body.entity_id},
            request=request,
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audit logging failed; mutation aborted")
    return {"status": "accepted", "message": "Rebuild enqueued. Poll /status for progress."}


@router.get("/claims")
def get_claims(
    entity_id: int | None = Query(None),
    claim_type: str | None = Query(None),
    _: AdminActor = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return memory claims with optional filters."""
    claims = list_claims(db=db, entity_id=entity_id, claim_type=claim_type)
    return [
        {
            "id": c.id,
            "claim_key": c.claim_key,
            "claim_type": c.claim_type,
            "entity_id": c.entity_id,
            "claim_value": c.claim_value,
            "confidence": c.confidence,
            "is_active": c.is_active,
            "source_snapshot_id": c.source_snapshot_id,
            "created_at": c.created_at,
        }
        for c in claims
    ]


@router.get("/entity/{entity_id}/state")
def get_entity_memory_state(
    entity_id: int,
    _: AdminActor = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict:
    """Return the current MemoryEntityState for a canonical entity."""
    state = get_entity_state(entity_id=entity_id, db=db)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No memory state found for entity {entity_id}",
        )
    return {
        "id": state.id,
        "entity_id": state.entity_id,
        "state_checksum": state.state_checksum,
        "display_name": state.display_name,
        "aliases": state.aliases,
        "roles": state.roles,
        "jurisdictions": state.jurisdictions,
        "biography_summary": state.biography_summary,
        "active_claim_count": state.active_claim_count,
        "rebuilt_at": state.rebuilt_at,
        "last_rebuild_run_id": state.last_rebuild_run_id,
    }


class InvalidateClaimRequest(BaseModel):
    reason: str = "manual_reject"


@router.post("/claims/{claim_id}/invalidate")
def invalidate_claim_endpoint(
    claim_id: int,
    body: InvalidateClaimRequest,
    request: Request,
    actor: AdminActor = Depends(require_admin_actor),
    db: Session = Depends(get_db),
) -> dict:
    """Manually invalidate a specific MemoryClaim."""
    enforce_jwt_mutation_authority(actor)
    try:
        audit = invalidate_claim(claim_id, body.reason, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        log_mutation(
            action="memory.claim.invalidate",
            entity_type="memory_claim",
            entity_id=str(claim_id),
            payload={"reason": body.reason, "audit_id": audit.id},
            request=request,
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
        "invalidated": True,
        "claim_id": claim_id,
        "reason": body.reason,
        "audit_id": audit.id,
    }
