"""Ingestion replay engine.

Replays a previous IngestionRun (or a partial run that was checkpointed)
by re-processing records from the stored checkpoint cursor.  The replay
engine delegates actual fetch+persist work back to the caller via a
callable so it remains adapter-agnostic.

Usage::

    def my_ingest(db, since, cursor):
        ...

    result = replay(db, source_name="courtlistener",
                    ingest_fn=my_ingest,
                    original_run_id=42)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.entities import IngestionRun
from app.ingestion.runtime import checkpointing, ingestion_log

_log = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    """Outcome of a replay attempt."""

    source_name: str
    original_run_id: int | None
    replay_run_id: int
    resumed_from_cursor: Any
    success: bool
    records_processed: int
    error: str | None = None


IngestFn = Callable[
    [Session, str, Any],  # (db, source_name, cursor) -> int (records processed)
    int,
]


def replay(
    db: Session,
    source_name: str,
    ingest_fn: IngestFn,
    *,
    original_run_id: int | None = None,
) -> ReplayResult:
    """Replay the last checkpointed state for *source_name*.

    Args:
        db:              Open SQLAlchemy session.
        source_name:     Logical source key (matches IngestionRun.source_name).
        ingest_fn:       Callable ``(db, source_name, cursor) -> records_int``.
                         The engine calls this once with the saved cursor.
        original_run_id: The run we are replaying (informational only).

    Returns:
        ReplayResult dataclass.
    """
    cursor = checkpointing.load(source_name)
    _log.info(
        "replay.start source=%s original_run_id=%s cursor=%r",
        source_name,
        original_run_id,
        cursor,
    )

    run = ingestion_log.open_run(db, source_name, pipeline_stage="replay")
    ingestion_log.set_stage(run, "replay")

    try:
        count = ingest_fn(db, source_name, cursor)
        ingestion_log.increment_counts(run, persisted=count)
        ingestion_log.close_run(db, run, status=ingestion_log.STATUS_COMPLETE)
        checkpointing.clear(source_name)
        _log.info("replay.complete source=%s records=%d", source_name, count)
        return ReplayResult(
            source_name=source_name,
            original_run_id=original_run_id,
            replay_run_id=run.id,
            resumed_from_cursor=cursor,
            success=True,
            records_processed=count,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("replay.failed source=%s", source_name)
        ingestion_log.append_error(run, str(exc))
        ingestion_log.close_run(db, run, status=ingestion_log.STATUS_FAILED)
        return ReplayResult(
            source_name=source_name,
            original_run_id=original_run_id,
            replay_run_id=run.id,
            resumed_from_cursor=cursor,
            success=False,
            records_processed=0,
            error=str(exc),
        )


def list_replayable(db: Session) -> list[dict[str, Any]]:
    """Return source names that have an uncommitted checkpoint (i.e. are replayable)."""
    active = checkpointing.list_active()
    return [
        {
            "source_name": entry["source_name"],
            "run_id": entry["run_id"],
            "cursor": entry["cursor"],
            "updated_at": entry["updated_at"],
        }
        for entry in active
    ]
