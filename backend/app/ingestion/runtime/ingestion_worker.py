"""Ingestion worker.

Executes a single end-to-end ingestion job for one adapter.  The worker
orchestrates:

1. Opening an ``IngestionRun`` record (via :mod:`ingestion_log`)
2. Loading the last checkpoint cursor (via :mod:`checkpointing`)
3. Starting a crawl state entry (via :mod:`crawl_state`)
4. Fetching and parsing records via the provided :class:`SourceAdapter`
5. Deduplication (via :mod:`dedupe`)
6. Persisting deduplicated records (via :func:`persistence.persist_parsed_record`)
7. Checkpointing progress after each batch
8. Recording health outcomes (via :mod:`source_health`)
9. Advancing the scheduler (via :mod:`source_scheduler`)

Deterministic, rule-based — no LLM calls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ingestion.adapters import ParsedRecord, SourceAdapter
from app.ingestion.persistence import PersistResult, persist_parsed_record
from app.models.entities import IngestionRun, SourceRegistry
from app.ingestion.runtime import (
    checkpointing,
    crawl_state,
    dedupe,
    ingestion_log,
    source_health,
    source_scheduler,
)

_log = logging.getLogger(__name__)

# How many records to persist between checkpoint saves
_CHECKPOINT_BATCH_SIZE = 50


class IngestionWorker:
    """Runs a single ingestion job to completion.

    Args:
        db:        Open SQLAlchemy session.
        adapter:   Configured :class:`SourceAdapter` for the source.
    """

    def __init__(self, db: Session, adapter: SourceAdapter) -> None:
        self.db = db
        self.adapter = adapter

    def run(
        self,
        source_name: str,
        since: datetime | None = None,
    ) -> IngestionRun:
        """Execute the full ingestion pipeline for *source_name*.

        Args:
            source_name: Logical source key (matches ``SourceRegistry.source_key``
                         and ``IngestionRun.source_name``).
            since:       Optional lower-bound datetime for the fetch window.
                         If ``None``, the checkpoint cursor is used (or the
                         adapter's own default if no checkpoint exists).

        Returns:
            The closed :class:`IngestionRun` ORM instance.
        """
        db = self.db
        adapter = self.adapter

        # ------------------------------------------------------------------
        # 0. Gate: verify source is registered and active
        # ------------------------------------------------------------------
        _reg = (
            db.query(SourceRegistry)
            .filter(SourceRegistry.source_key == source_name)
            .first()
        )
        if _reg is None:
            raise RuntimeError(
                f"ingestion_worker: unknown source_key={source_name!r} — "
                "register the source in SourceRegistry before running"
            )
        if not _reg.is_active:
            raise RuntimeError(
                f"ingestion_worker: source {source_name!r} is_active=False — "
                "activate the source in SourceRegistry before running"
            )

        # ------------------------------------------------------------------
        # 1. Open run
        # ------------------------------------------------------------------
        run = ingestion_log.open_run(db, source_name, pipeline_stage="fetch")
        _log.info("worker.start source=%s run_id=%s", source_name, run.id)

        try:
            # --------------------------------------------------------------
            # 2. Determine effective cursor
            # --------------------------------------------------------------
            cursor = checkpointing.load(source_name)
            effective_since: datetime | None = since
            if cursor is not None and isinstance(cursor, dict) and "since" in cursor:
                try:
                    effective_since = datetime.fromisoformat(cursor["since"])
                except (TypeError, ValueError):
                    pass  # fall back to the provided `since`

            # --------------------------------------------------------------
            # 3. Start crawl state
            # --------------------------------------------------------------
            crawl_state.start(source_name, initial_cursor=cursor)

            # --------------------------------------------------------------
            # 4. Fetch raw records
            # --------------------------------------------------------------
            ingestion_log.set_stage(run, "fetch")
            fetch_since = effective_since or datetime.now(tz=timezone.utc)
            raw_records = adapter.fetch(fetch_since)
            fetched_count = len(raw_records)
            ingestion_log.increment_counts(run, fetched=fetched_count)
            _log.info(
                "worker.fetched source=%s count=%d since=%s",
                source_name,
                fetched_count,
                fetch_since.isoformat(),
            )

            # --------------------------------------------------------------
            # 5. Parse + dedupe + persist (in batches)
            # --------------------------------------------------------------
            ingestion_log.set_stage(run, "parse")
            parsed_total = 0
            persisted_total = 0
            skipped_total = 0
            error_total = 0
            batch_count = 0

            for raw in raw_records:
                try:
                    parsed_list: list[ParsedRecord] = adapter.parse_many(raw)
                except Exception as exc:  # noqa: BLE001
                    ingestion_log.append_error(
                        run,
                        f"parse_error: {exc}",
                        payload={"payload": str(raw.payload)[:256]},
                    )
                    error_total += 1
                    continue

                for parsed in parsed_list:
                    parsed_total += 1
                    try:
                        # Deduplicate
                        dedup = dedupe.check_parsed_record(db, parsed)
                        if dedup.is_duplicate:
                            skipped_total += 1
                            continue

                        # Persist
                        result: PersistResult = persist_parsed_record(db, parsed)
                        if result.persisted:
                            persisted_total += 1
                        else:
                            skipped_total += 1
                    except Exception as exc:  # noqa: BLE001
                        ingestion_log.append_error(
                            run,
                            f"persist_error: {exc}",
                            payload={"docket_id": parsed.docket_id},
                        )
                        error_total += 1

                # Checkpoint after each batch of _CHECKPOINT_BATCH_SIZE
                batch_count += 1
                if batch_count % _CHECKPOINT_BATCH_SIZE == 0:
                    new_cursor = {
                        "since": fetch_since.isoformat(),
                        "offset": batch_count,
                    }
                    checkpointing.save(source_name, new_cursor, run_id=run.id)
                    crawl_state.advance(
                        source_name, new_cursor, fetched_count=batch_count
                    )

            # Final counts
            ingestion_log.increment_counts(
                run,
                parsed=parsed_total,
                persisted=persisted_total,
                skipped=skipped_total,
                errors=error_total,
            )

            # --------------------------------------------------------------
            # 6. Close run
            # --------------------------------------------------------------
            final_status = (
                ingestion_log.STATUS_PARTIAL
                if error_total > 0 and persisted_total > 0
                else (
                    ingestion_log.STATUS_FAILED
                    if error_total > 0 and persisted_total == 0
                    else ingestion_log.STATUS_COMPLETE
                )
            )
            ingestion_log.close_run(db, run, status=final_status)
            checkpointing.clear(source_name)
            crawl_state.finish(source_name)

            # --------------------------------------------------------------
            # 7. Health + scheduler
            # --------------------------------------------------------------
            if final_status in (
                ingestion_log.STATUS_COMPLETE,
                ingestion_log.STATUS_PARTIAL,
            ):
                source_health.record_success(source_name, run_id=run.id)
            else:
                source_health.record_failure(source_name, run_id=run.id)
            source_scheduler.mark_ran(source_name)

            _log.info(
                "worker.complete source=%s run_id=%s status=%s persisted=%d skipped=%d errors=%d",
                source_name,
                run.id,
                final_status,
                persisted_total,
                skipped_total,
                error_total,
            )
            return run

        except Exception as exc:  # noqa: BLE001
            _log.exception("worker.fatal source=%s run_id=%s", source_name, run.id)
            ingestion_log.append_error(run, f"fatal: {exc}")
            ingestion_log.close_run(db, run, status=ingestion_log.STATUS_FAILED)
            source_health.record_failure(source_name, run_id=run.id, error=str(exc))
            source_scheduler.mark_ran(source_name)
            crawl_state.finish(source_name)
            return run
