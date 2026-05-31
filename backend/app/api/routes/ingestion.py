from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.auth.admin import enforce_jwt_mutation_authority, log_mutation
from app.auth.actor import AdminActor
from app.core.config import get_settings
from app.core.rate_limit import rate_limit_ingestion
from app.core.request_utils import read_upload_file_limited
from app.db.session import get_db
from app.ingestion.runner import run_courtlistener_ingestion
from app.security.import_authority import require_source_admin_actor
from app.models.entities import IngestionRun

router = APIRouter()


@router.post(
    "/api/admin/import/crime-incidents/manual-csv",
    dependencies=[Depends(rate_limit_ingestion)],
)
async def import_crime_incidents_manual_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
):
    """Import crime incidents from CSV with size limits.

    This is an explicit admin-only override that intentionally bypasses SourceRegistry.
    Manual CSV imports are direct admin actions, not automated ingestion pipelines,
    so runtime gating via SourceRegistry is not applicable here.
    All imported records start with public_visibility=False (or equivalent default)
    and require human review before any public-facing exposure.
    Access is restricted to admin tokens via require_admin_imports.
    """
    enforce_jwt_mutation_authority(actor)
    settings = get_settings()

    # Lazy import: crime_sources is an experimental package (NOT_RUNTIME) gated by require_admin_imports.
    from app.ingestion.crime_sources.manual_csv import (
        import_crime_incidents_csv,
    )  # noqa: PLC0415

    # Read file with size limit enforcement
    content = await read_upload_file_limited(file, settings.max_csv_upload_size)
    text = content.decode("utf-8-sig")
    result = import_crime_incidents_csv(db, StringIO(text), commit=False)
    try:
        log_mutation(
            action="manual_csv_import",
            entity_type="crime_incident",
            actor=actor,
            payload={
                "persisted": result.persisted_count,
                "skipped": result.skipped_count,
            },
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return {
        "read_count": result.read_count,
        "persisted_count": result.persisted_count,
        "skipped_count": result.skipped_count,
        "error_count": result.error_count,
        "errors": result.errors,
    }


@router.post("/api/ingest/courtlistener", dependencies=[Depends(rate_limit_ingestion)])
def ingest_courtlistener(
    since: datetime = Query(...),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
):
    enforce_jwt_mutation_authority(actor)
    run: IngestionRun = run_courtlistener_ingestion(db, since, commit=False)
    try:
        log_mutation(
            action="courtlistener_ingest",
            entity_type="ingestion_run",
            entity_id=str(run.id),
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Audit logging failed; mutation aborted"
        )
    return {
        "id": run.id,
        "status": run.status,
        "fetched_count": run.fetched_count,
        "parsed_count": run.parsed_count,
        "persisted_count": run.persisted_count,
        "skipped_count": run.skipped_count,
        "error_count": run.error_count,
        "errors": run.errors or [],
    }
