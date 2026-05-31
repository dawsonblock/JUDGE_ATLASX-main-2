"""Admin quarantine management endpoints.

Operators use these endpoints to inspect ingestion runs that have been
flagged as quarantined and to release them for retry or archival.

Routes
------
GET  /api/admin/quarantine          List all quarantined runs
POST /api/admin/quarantine/{id}/release  Release a quarantined run
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.admin import (
    enforce_jwt_mutation_authority,
    log_mutation,
    require_admin_token,
)
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.ingestion.quarantine import list_quarantined, release_from_quarantine
from app.security.import_authority import require_admin_actor

router = APIRouter(prefix="/api/admin/quarantine", tags=["admin"])


class QuarantinedRunOut(BaseModel):
    """Serialization schema for a quarantined IngestionRun."""

    id: int
    source_name: str
    status: str
    pipeline_stage: str | None
    quarantine_reason: str | None
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    parsed_count: int
    persisted_count: int
    error_count: int

    model_config = ConfigDict(from_attributes=True)


class ReleaseResponse(BaseModel):
    """Confirmation payload returned after releasing a run."""

    id: int
    status: str
    pipeline_stage: str | None
    message: str


@router.get("", response_model=list[QuarantinedRunOut])
def get_quarantined_runs(
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_token),
) -> list[QuarantinedRunOut]:
    """List all ingestion runs currently in quarantine.

    Returns runs ordered by started_at descending (most recent first).

    Security: requires admin token.
    """
    runs = list_quarantined(db)
    return [QuarantinedRunOut.model_validate(r) for r in runs]


@router.post("/{run_id}/release", response_model=ReleaseResponse)
def release_run(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_actor),
) -> ReleaseResponse:
    """Release a quarantined ingestion run.

    Clears the quarantine stage and reason so the run can be retried
    or archived.  Sets status to 'released'.

    Security: requires admin token and JWT authorization for mutations.

    Raises:
        404: Run not found.
        422: Run is not currently quarantined.
    """
    enforce_jwt_mutation_authority(actor)
    try:
        run = release_from_quarantine(db, run_id)
        log_mutation(
            action="quarantine.release",
            entity_type="ingestion_run",
            entity_id=str(run.id),
            payload={
                "run_id": run.id,
                "status": run.status,
                "pipeline_stage": run.pipeline_stage,
            },
            request=request,
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Audit logging failed; mutation aborted",
        )

    return ReleaseResponse(
        id=run.id,
        status=run.status,
        pipeline_stage=run.pipeline_stage,
        message=f"IngestionRun {run_id} released from quarantine.",
    )
