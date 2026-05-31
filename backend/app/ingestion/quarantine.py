"""Quarantine management for failed or suspicious ingestion runs.

An ingestion run transitions to pipeline_stage='quarantine' when the runner
catches an unhandled exception or when a downstream validation step flags the
run as unsafe to persist.  Quarantined runs are held for operator review and
must be explicitly released or discarded.

Public API
----------
quarantine_run(db, run, reason)
    Mark a run as quarantined with an explanatory reason string.

list_quarantined(db) -> list[IngestionRun]
    Return all runs currently in quarantine (pipeline_stage='quarantine').

release_from_quarantine(db, run_id) -> IngestionRun
    Clear the quarantine flag so the run can be retried or archived.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import IngestionRun
from app.ingestion.statuses import FAILED

_QUARANTINE_STAGE = "quarantine"


def quarantine_run(db: Session, run: IngestionRun, reason: str) -> None:
    """Mark *run* as quarantined and record the human-readable *reason*.

    The run's ``status`` is also set to ``'failed'`` so that callers that
    inspect only the status column still see a terminal state.

    Args:
        db:     Active database session (no commit performed).
        run:    The IngestionRun instance to quarantine.
        reason: Free-text explanation (exception message, validation failure,
                operator note, etc.).
    """
    run.pipeline_stage = _QUARANTINE_STAGE
    run.quarantine_reason = reason
    run.status = FAILED
    db.flush()


def list_quarantined(db: Session) -> list[IngestionRun]:
    """Return all ingestion runs currently in quarantine.

    Args:
        db: Active database session.

    Returns:
        List of IngestionRun objects with pipeline_stage='quarantine',
        ordered by started_at descending (most recent first).
    """
    stmt = (
        select(IngestionRun)
        .where(IngestionRun.pipeline_stage == _QUARANTINE_STAGE)
        .order_by(IngestionRun.started_at.desc())
    )
    return list(db.scalars(stmt).all())


def release_from_quarantine(db: Session, run_id: int) -> IngestionRun:
    """Release a quarantined run so it can be retried or archived.

    Clears ``pipeline_stage`` and ``quarantine_reason``.  The ``status`` is
    set to ``'released'`` so downstream monitoring can distinguish released
    runs from runs that succeeded or were freshly quarantined.

    Args:
        db:     Active database session.
        run_id: Primary key of the IngestionRun to release.

    Returns:
        The updated IngestionRun.

    Raises:
        ValueError: If no run with *run_id* exists or the run is not
            currently in quarantine.
    """
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise ValueError(f"IngestionRun {run_id} not found")
    if run.pipeline_stage != _QUARANTINE_STAGE:
        raise ValueError(
            f"IngestionRun {run_id} is not quarantined "
            f"(current stage: {run.pipeline_stage!r})"
        )
    run.pipeline_stage = None
    run.quarantine_reason = None
    run.status = "released"
    db.flush()
    return run
