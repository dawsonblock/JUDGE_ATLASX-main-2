"""Validate that a replay of ingested data produces consistent evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.models.entities import IngestionRun, SourceSnapshot
from app.ingestion.statuses import COMPLETED


@dataclass
class ReplayValidationResult:
    ok: bool
    runs_checked: int
    runs_without_snapshot: list[int] = field(default_factory=list)


def validate_run_snapshots(db: Session) -> ReplayValidationResult:
    """Every completed IngestionRun that produced records must have a snapshot."""
    runs = (
        db.query(IngestionRun)
        .filter(IngestionRun.status == COMPLETED)
        .all()
    )
    missing: list[int] = []
    for run in runs:
        if run.persisted_count and run.persisted_count > 0:
            snap = (
                db.query(SourceSnapshot.id)
                .filter(SourceSnapshot.ingestion_run_id == run.id)
                .first()
            )
            if snap is None:
                missing.append(run.id)

    return ReplayValidationResult(
        ok=len(missing) == 0,
        runs_checked=len(runs),
        runs_without_snapshot=missing,
    )
