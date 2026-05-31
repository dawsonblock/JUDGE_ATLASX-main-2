"""Worker job: ingestion_run.

Executes a single ingestion run for a named source in a controlled, auditable
manner.  This job is the canonical execution path for machine_ingest adapters.

Usage (enqueue via WorkersRuntime)::

    from app.workers.jobs.ingestion_run import INGESTION_RUN_JOB, run_ingestion_job
    from app.workers.workers_runtime import WorkersRuntime

    runtime = WorkersRuntime()
    runtime.registry.register(INGESTION_RUN_JOB, run_ingestion_job)
    runtime.router.register(INGESTION_RUN_JOB)
    job_id = runtime.submit(INGESTION_RUN_JOB, {"source_key": "federal_court_canada"})

The job enforces:
1. source_class == machine_ingest
2. is_active == true
3. allowed_domains and parser are set
4. raw evidence bytes are preserved in the result
5. IngestionRun record is created/updated
6. source health is updated after every run
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

INGESTION_RUN_JOB = "ingestion_run"

_RUNNABLE_CLASS = "machine_ingest"


def run_ingestion_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute an ingestion run for the source identified by ``payload["source_key"]``.

    Parameters
    ----------
    payload:
        Must contain ``source_key``.  Optional: ``limit`` (int).

    Returns
    -------
    dict with keys: ok, source_key, run_id, status, records_fetched,
    review_items, created_records, errors, raw_snapshot_preserved.
    """
    source_key: str = payload.get("source_key", "")
    if not source_key:
        return {
            "ok": False,
            "error_code": "MISSING_SOURCE_KEY",
            "message": "payload must contain source_key",
        }

    # Import here to avoid circular imports at module level.
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.ingestion.source_adapter_factory import build_adapter
    from app.ingestion.source_registry_ctl import update_source_health
    from app.ingestion.source_runner import persist_ingestion_result
    from app.ingestion.statuses import COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, RUNNING
    from app.models.entities import IngestionRun, SourceRegistry

    with SessionLocal() as db:
        source = db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if source is None:
            return {
                "ok": False,
                "error_code": "SOURCE_NOT_FOUND",
                "source_key": source_key,
                "message": f"Source '{source_key}' not found in registry.",
            }

        # Guard 1: must be machine_ingest.
        if source.source_class != _RUNNABLE_CLASS:
            return {
                "ok": False,
                "error_code": "SOURCE_NOT_RUNNABLE",
                "source_key": source_key,
                "source_class": source.source_class,
                "message": (
                    f"Source '{source_key}' has class '{source.source_class}' "
                    "and cannot be auto-ingested."
                ),
                "next_action": "Only machine_ingest sources may be run.",
            }

        # Guard 2: must be active.
        if not source.is_active:
            return {
                "ok": False,
                "error_code": "SOURCE_NOT_ACTIVE",
                "source_key": source_key,
                "message": f"Source '{source_key}' is disabled; enable it before running.",
                "next_action": "Use 'judgectl sources enable SOURCE_KEY --yes' to enable.",
            }

        # Guard 3: must have allowed_domains set.
        if not source.allowed_domains or source.allowed_domains == "[]":
            return {
                "ok": False,
                "error_code": "SOURCE_MISSING_ALLOWED_DOMAINS",
                "source_key": source_key,
                "message": f"Source '{source_key}' has no allowed_domains configured.",
                "next_action": "Set allowed_domains in the source registry before running.",
            }

        # Guard 4: must have a parser.
        if not source.parser:
            return {
                "ok": False,
                "error_code": "SOURCE_MISSING_PARSER",
                "source_key": source_key,
                "message": f"Source '{source_key}' has no parser configured.",
                "next_action": "Set parser in the source registry before running.",
            }

        # Build adapter.
        settings = get_settings()
        adapter = build_adapter(source, settings)
        if adapter is None:
            return {
                "ok": False,
                "error_code": "NO_ADAPTER",
                "source_key": source_key,
                "parser": source.parser,
                "message": f"No adapter registered for parser '{source.parser}'.",
            }

        # Create IngestionRun record.
        run_record = IngestionRun(
            source_name=source_key,
            started_at=datetime.now(timezone.utc),
            status=RUNNING,
        )
        db.add(run_record)
        db.commit()
        db.refresh(run_record)
        run_id = run_record.id

        # Execute adapter.
        try:
            result = adapter.run()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Adapter error for source %s", source_key)
            run_record.status = FAILED
            run_record.finished_at = datetime.now(timezone.utc)
            run_record.error_count = 1
            db.commit()
            update_source_health(db, source_key, run_record)
            db.commit()
            return {
                "ok": False,
                "error_code": "ADAPTER_ERROR",
                "source_key": source_key,
                "run_id": run_id,
                "message": str(exc),
            }

        # Detect missing API key errors — these should be hard failures, not
        # silent completed_with_warnings runs that look like success.
        missing_key_errors = [
            e for e in result.errors
            if "api_key" in e.lower() or "api key" in e.lower() or "CANLII_API_KEY" in e
        ]
        if missing_key_errors:
            run_record.status = FAILED
            run_record.finished_at = datetime.now(timezone.utc)
            run_record.error_count = len(result.errors)
            db.commit()
            update_source_health(db, source_key, run_record)
            db.commit()
            return {
                "ok": False,
                "error_code": "MISSING_API_KEY",
                "source_key": source_key,
                "run_id": run_id,
                "message": missing_key_errors[0],
                "next_action": (
                    f"Set the required API key environment variable before running '{source_key}'."
                ),
            }

        # Check evidence bytes contract.
        raw_snapshot_preserved = bool(result.raw_snapshot_bytes)
        if not raw_snapshot_preserved:
            logger.warning(
                "Source %s adapter returned no raw_snapshot_bytes; "
                "evidence provenance is incomplete.",
                source_key,
            )

        # Persist results.
        run_record.status = COMPLETED if result.success else COMPLETED_WITH_WARNINGS
        run_record.finished_at = datetime.now(timezone.utc)
        run_record.fetched_count = result.records_fetched
        run_record.parsed_count = (
            len(result.created_records)
            + len(result.legal_instruments)
            + len(result.review_items)
        )
        run_record.skipped_count = result.records_skipped
        run_record.error_count = len(result.errors)
        run_record.errors = result.errors or None

        persist_summary = persist_ingestion_result(db, source, run_record, result)
        db.commit()
        update_source_health(db, source_key, run_record)
        db.commit()

        return {
            "ok": True,
            "source_key": source_key,
            "run_id": run_id,
            "status": run_record.status,
            "records_fetched": result.records_fetched,
            "review_items": persist_summary.persisted_review_items,
            "legal_instruments": persist_summary.persisted_legal_instruments,
            "created_records": persist_summary.persisted_incidents,
            "skipped_duplicates": persist_summary.skipped_duplicates,
            "errors": result.errors,
            "raw_snapshot_preserved": raw_snapshot_preserved,
        }
