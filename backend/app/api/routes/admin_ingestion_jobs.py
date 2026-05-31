"""Admin ingestion queue job endpoints.

Provides visibility and control for queued ingestion runs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth.admin import enforce_jwt_mutation_authority, log_mutation, require_admin_token
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.security.import_authority import require_source_admin_actor
from app.workers.ingestion_queue import get_ingestion_queue
from app.workers.queue_backend import JobState

router = APIRouter(prefix="/api/admin/ingestion-jobs", tags=["admin"])


class IngestionJobResponse(BaseModel):
    job_id: str
    source_key: str
    state: str
    enqueued_at: float
    started_at: float | None
    finished_at: float | None
    run_id: int | None
    records_fetched: int
    review_items: int
    created_records: int
    raw_snapshot_preserved: bool
    error: str | None


class RetryJobResponse(BaseModel):
    old_job_id: str
    new_job_id: str
    source_key: str
    state: JobState = JobState.PENDING


def _serialize_job(record: Any) -> IngestionJobResponse:
    return IngestionJobResponse(**record.to_dict())


@router.get("", response_model=list[IngestionJobResponse])
def list_ingestion_jobs(
    state: JobState | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    _: AdminActor = Depends(require_admin_token),
) -> list[IngestionJobResponse]:
    queue = get_ingestion_queue()
    jobs = queue.list_jobs(state)
    return [_serialize_job(job) for job in jobs[:limit]]


@router.get("/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(job_id: str, _: AdminActor = Depends(require_admin_token)) -> IngestionJobResponse:
    queue = get_ingestion_queue()
    job = queue.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return _serialize_job(job)


@router.post("/{job_id}/cancel", response_model=IngestionJobResponse)
def cancel_ingestion_job(
    job_id: str,
    request: Request,
    db = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> IngestionJobResponse:
    enforce_jwt_mutation_authority(actor)
    queue = get_ingestion_queue()
    job = queue.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is already {job.state.value} and cannot be canceled.",
        )

    try:
        canceled = queue.cancel_job(job_id, error="Canceled by admin")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if canceled is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    refreshed = queue.get_status(job_id) or canceled

    log_mutation(
        action="ingestion.job.cancel",
        entity_type="ingestion_queue_job",
        entity_id=job_id,
        payload={"job_id": job_id, "source_key": refreshed.source_key},
        request=request,
        actor=actor,
        db=db,
        fail_closed=True,
    )

    return _serialize_job(refreshed)


@router.post("/{job_id}/retry", response_model=RetryJobResponse)
def retry_ingestion_job(
    job_id: str,
    request: Request,
    db = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> RetryJobResponse:
    enforce_jwt_mutation_authority(actor)
    queue = get_ingestion_queue()
    old_job = queue.get_status(job_id)
    if not old_job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if old_job.state not in (JobState.FAILED, JobState.COMPLETED, JobState.CANCELLED):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' must be completed or failed before retry.",
        )

    try:
        new_job_id = queue.retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not new_job_id:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    log_mutation(
        action="ingestion.job.retry",
        entity_type="ingestion_queue_job",
        entity_id=job_id,
        payload={
            "old_job_id": job_id,
            "new_job_id": new_job_id,
            "source_key": old_job.source_key,
        },
        request=request,
        actor=actor,
        db=db,
        fail_closed=True,
    )

    return RetryJobResponse(
        old_job_id=job_id,
        new_job_id=new_job_id,
        source_key=old_job.source_key,
        state=JobState.PENDING,
    )
