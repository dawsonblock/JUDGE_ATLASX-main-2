"""Admin ingestion endpoint (Canada-first).

Triggers manual ingestion runs for Canada-first open-data sources.
Guarded by JTA_ENABLE_ADMIN_IMPORTS and admin token.

Legacy U.S. ingestion routes have been moved to admin_legacy_ingest.py
and are disabled by default. Enable via JTA_ENABLE_LEGACY_US_INGEST_ROUTES.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth.admin import enforce_jwt_mutation_authority, log_mutation
from app.auth.actor import AdminActor
from app.core.config import get_settings
from app.core.request_utils import read_upload_file_limited
from app.db.session import get_db
from app.ingestion.crime_sources.saskatoon import import_saskatoon_csv
from app.ingestion.source_keys import resolve_source_key
from app.ingestion.automation_statuses import BLOCK_SOURCE_INACTIVE
from app.ingestion.source_registry_ctl import (
    check_ingestion_allowed,
    require_source_registry,
)
from app.ingestion.run_audit import record_failed_ingestion_attempt
from app.security.import_authority import require_source_admin_actor

router = APIRouter(prefix="/api/admin/ingest", tags=["admin"])


def _check_csv_row_limit(content: bytes, max_rows: int, source: str) -> None:
    """Raise HTTP 422 if the CSV byte content exceeds the row-count cap.

    Uses newline count as a fast O(n) proxy; subtracts 1 for the header row.
    Raises before the importer processes any rows, preventing DoS via huge
    CSVs that pass the byte-size check but contain millions of tiny rows.
    """
    row_count = content.count(b"\n")
    if row_count > max_rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{source} CSV exceeds the maximum allowed row count "
                f"({row_count:,} rows found, limit is {max_rows:,}). "
                "Split the file and re-upload in batches."
            ),
        )


def _check_source_active(source_key: str, source_name: str, db: Session) -> None:
    """Raise HTTP 403 if the source is disabled in SourceRegistry."""
    registry = require_source_registry(db, source_key, source_name)
    allowed, reason = check_ingestion_allowed(registry)
    if not allowed:
        error_code, _, error_msg = reason.partition("::")
        if error_code != BLOCK_SOURCE_INACTIVE:
            return
        failed_run = record_failed_ingestion_attempt(
            db,
            source_key=source_key,
            error_code=error_code,
            error_message=error_msg or reason,
            stage="admin_ingest.validation",
        )
        disabled_reason = error_msg or "Source is disabled"
        raise HTTPException(
            status_code=403,
            detail=f"{disabled_reason} (failed_run_id={failed_run.id})",
        )


@router.post("/saskatoon")
async def ingest_saskatoon(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
):
    """Import Saskatoon Police CSV upload (Canada-first source)."""
    enforce_jwt_mutation_authority(actor)

    settings = get_settings()
    if not settings.local_feeds_enabled:
        raise HTTPException(
            status_code=403,
            detail=(
                "Local feeds circuit breaker off (set JTA_LOCAL_FEEDS_ENABLED=true). "
                "Ensure source is also active in SourceRegistry."
            ),
        )
    source_key = resolve_source_key("saskatoon_crime")
    _check_source_active(source_key, "Saskatoon Police Service", db)
    content = await read_upload_file_limited(file, settings.max_csv_upload_size)
    _check_csv_row_limit(content, settings.max_csv_rows, "Saskatoon")
    stream = io.StringIO(content.decode("utf-8-sig"))
    result = import_saskatoon_csv(db, stream, commit=False)

    try:
        log_mutation(
            action="ingest.saskatoon",
            entity_type="ingestion_run",
            entity_id=str(result.run_id) if hasattr(result, "run_id") else None,
            payload={
                "filename": file.filename,
                "persisted_count": result.persisted_count,
                "skipped_count": result.skipped_count,
            },
            request=request,
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

    return result.__dict__
