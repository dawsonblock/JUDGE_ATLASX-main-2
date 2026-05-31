"""Ingestion runtime — top-level dependency-injection container.

Wires together all ingestion runtime components and provides a single
entry-point for running ingestion jobs.

Usage::

    from sqlalchemy.orm import Session
    from app.ingestion.runtime.ingestion_runtime import IngestionRuntime

    def ingest(db: Session, adapter):
        runtime = IngestionRuntime(db)
        runtime.scheduler.register("courtlistener", interval_seconds=3600)
        for source_name in runtime.scheduler.due_sources():
            worker = runtime.get_worker(adapter)
            run = worker.run(source_name)

Deterministic, rule-based — no LLM calls.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ingestion.adapters import SourceAdapter
from app.models.entities import IngestionRun
from app.ingestion.runtime import (
    checkpointing,
    crawl_state,
    dedupe,
    replay_engine,
    retry_queue,
    source_health,
    source_scheduler,
)
from app.ingestion.runtime.ingestion_worker import IngestionWorker
from app.ingestion.runtime.replay_engine import ReplayResult

_log = logging.getLogger(__name__)


class IngestionRuntime:
    """Top-level container for all ingestion runtime services.

    All component references point to the module-level singletons so that
    multiple :class:`IngestionRuntime` instances within the same process share
    state (as intended — scheduling and health data are process-global).

    Args:
        db: Open SQLAlchemy session.  Passed through to workers and replay.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        # Expose module references as attributes for callers
        self.scheduler = source_scheduler
        self.health = source_health
        self.retry = retry_queue
        self.crawl = crawl_state
        self.checkpointing = checkpointing

    # ------------------------------------------------------------------
    # Worker factory
    # ------------------------------------------------------------------

    def get_worker(self, adapter: SourceAdapter) -> IngestionWorker:
        """Return a configured :class:`IngestionWorker` for *adapter*.

        Args:
            adapter: The :class:`SourceAdapter` to use for fetch/parse.

        Returns:
            A new :class:`IngestionWorker` bound to this runtime's DB session.
        """
        return IngestionWorker(self._db, adapter)

    # ------------------------------------------------------------------
    # Replay support
    # ------------------------------------------------------------------

    def can_replay(self, source_name: str) -> bool:
        """Return ``True`` if a checkpoint exists for *source_name*."""
        return checkpointing.load(source_name) is not None

    def replay(
        self,
        source_name: str,
        adapter: SourceAdapter,
        *,
        original_run_id: int | None = None,
    ) -> ReplayResult:
        """Replay the last checkpointed state for *source_name*.

        Internally this calls :func:`replay_engine.replay` with an ingest
        function that delegates to a fresh :class:`IngestionWorker`.

        Args:
            source_name:     Source to replay.
            adapter:         Adapter to use for the replay fetch.
            original_run_id: The failed run being replayed (informational).

        Returns:
            :class:`ReplayResult` dataclass.
        """

        def _ingest_fn(db: Session, sn: str, cursor: Any) -> int:
            worker = IngestionWorker(db, adapter)
            run = worker.run(sn)
            return run.persisted_count or 0

        return replay_engine.replay(
            self._db,
            source_name,
            _ingest_fn,
            original_run_id=original_run_id,
        )

    # ------------------------------------------------------------------
    # Convenience: list replayable sources
    # ------------------------------------------------------------------

    def list_replayable(self) -> list[dict[str, Any]]:
        """Return sources that have uncommitted checkpoints."""
        return replay_engine.list_replayable(self._db)

    # ------------------------------------------------------------------
    # Health / scheduler convenience
    # ------------------------------------------------------------------

    def due_sources(self, at: datetime | None = None) -> list[str]:
        """Return source names due for a run according to the scheduler."""
        return source_scheduler.due_sources(at=at)

    def is_healthy(
        self, source_name: str, *, max_consecutive_failures: int = 3
    ) -> bool:
        """Return ``True`` if *source_name* is considered healthy."""
        return source_health.is_healthy(
            source_name, max_consecutive_failures=max_consecutive_failures
        )
