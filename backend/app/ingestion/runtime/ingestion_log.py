"""Structured logging wrapper for ingestion run lifecycle.

Records per-run phase transitions and error events against the
existing IngestionRun ORM row.  All writes are in-session; the caller
is responsible for session.commit().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import IngestionRun
from app.ingestion.statuses import COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, QUARANTINED, RUNNING

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status constants (mirrors IngestionRun.status column values)
# ---------------------------------------------------------------------------

STATUS_RUNNING = RUNNING
STATUS_COMPLETE = COMPLETED
STATUS_FAILED = FAILED
STATUS_QUARANTINED = QUARANTINED
STATUS_PARTIAL = COMPLETED_WITH_WARNINGS


def open_run(
    db: Session,
    source_name: str,
    *,
    pipeline_stage: str | None = None,
) -> IngestionRun:
    """Create and persist a new IngestionRun row.

    Returns the committed row (id is populated after flush).
    """
    run = IngestionRun(
        source_name=source_name,
        started_at=datetime.now(timezone.utc),
        status=STATUS_RUNNING,
        pipeline_stage=pipeline_stage,
        fetched_count=0,
        parsed_count=0,
        persisted_count=0,
        skipped_count=0,
        error_count=0,
        errors=[],
    )
    db.add(run)
    db.flush()  # populate run.id without full commit
    _log.info("ingestion.run.open source=%s run_id=%s", source_name, run.id)
    return run


def close_run(
    db: Session,
    run: IngestionRun,
    *,
    status: str = STATUS_COMPLETE,
) -> None:
    """Mark the run finished and stamp finished_at."""
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    _log.info(
        "ingestion.run.close run_id=%s status=%s fetched=%d persisted=%d errors=%d",
        run.id,
        status,
        run.fetched_count,
        run.persisted_count,
        run.error_count,
    )


def increment_counts(
    run: IngestionRun,
    *,
    fetched: int = 0,
    parsed: int = 0,
    persisted: int = 0,
    skipped: int = 0,
    errors: int = 0,
) -> None:
    """Increment counters on a live IngestionRun row."""
    run.fetched_count = (run.fetched_count or 0) + fetched
    run.parsed_count = (run.parsed_count or 0) + parsed
    run.persisted_count = (run.persisted_count or 0) + persisted
    run.skipped_count = (run.skipped_count or 0) + skipped
    run.error_count = (run.error_count or 0) + errors


def append_error(
    run: IngestionRun,
    message: str,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a structured error entry to run.errors (JSON list)."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "msg": message,
    }
    if payload:
        entry["payload"] = payload
    errors = list(run.errors or [])
    errors.append(entry)
    run.errors = errors
    run.error_count = len(errors)
    _log.warning("ingestion.run.error run_id=%s msg=%s", run.id, message)


def set_stage(run: IngestionRun, stage: str) -> None:
    """Update the current pipeline_stage on the run."""
    run.pipeline_stage = stage
    _log.debug("ingestion.run.stage run_id=%s stage=%s", run.id, stage)
