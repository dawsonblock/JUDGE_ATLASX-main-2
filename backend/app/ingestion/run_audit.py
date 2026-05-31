"""Helpers for recording ingestion attempt audit rows.

This module records FAILED ``IngestionRun`` rows for blocked attempts that fail
validation before adapter execution starts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ingestion.statuses import FAILED
from app.models.entities import IngestionRun


def record_failed_ingestion_attempt(
    db: Session,
    *,
    source_key: str,
    error_code: str,
    error_message: str,
    stage: str = "validation",
) -> IngestionRun:
    """Persist a FAILED ingestion run row for a blocked attempt.

    Args:
        db: SQLAlchemy database session.
        source_key: Source key associated with the blocked attempt.
        error_code: Stable reason code (for example ``SOURCE_INACTIVE``).
        error_message: Human-readable blocker message.
        stage: Pipeline stage prefix used to annotate ``pipeline_stage``.

    Returns:
        The persisted ``IngestionRun`` row.
    """
    now = datetime.now(timezone.utc)
    run = IngestionRun(
        source_name=source_key,
        started_at=now,
        finished_at=now,
        status=FAILED,
        fetched_count=0,
        parsed_count=0,
        persisted_count=0,
        skipped_count=0,
        error_count=1,
        errors=[f"{error_code}: {error_message}"],
        pipeline_stage=f"{stage}.{error_code}",
    )
    db.add(run)
    db.flush()
    db.commit()
    db.refresh(run)
    return run