"""judgectl ingest — run and check ingestion jobs."""

from __future__ import annotations

from datetime import datetime, timezone

import click

from app.cli.db import get_db_session
from app.cli.output import emit, emit_error
from app.core.config import get_settings
from app.ingestion.source_keys import SK_COURTS_CA_DECISIONS, SK_COURTS_QB_DECISIONS
from app.ingestion.statuses import RUNNING
from app.models.entities import IngestionRun, SourceRegistry


@click.group()
def ingest() -> None:
    """Ingestion run management."""


@ingest.command("enqueue")
@click.argument("source_key")
@click.pass_context
def ingest_enqueue(ctx: click.Context, source_key: str) -> None:
    """Enqueue an ingestion job for SOURCE_KEY (preferred for production use)."""
    as_json: bool = ctx.obj.get("as_json", False)
    from app.ingestion.source_registry_ctl import check_ingestion_allowed

    with get_db_session() as db:
        row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if row is None:
            emit_error(
                f"Source '{source_key}' not found.",
                command="ingest.enqueue",
                error_code="SOURCE_NOT_FOUND",
                next_action="Run 'judgectl sources list' to see available sources.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)
        allowed, reason = check_ingestion_allowed(row)
        if not allowed:
            emit_error(
                f"Source '{source_key}' cannot be enqueued: {reason}",
                command="ingest.enqueue",
                error_code="SOURCE_NOT_RUNNABLE",
                next_action=f"Enable or repair source first: judgectl sources info {source_key}",
                source_key=source_key,
                block_reason=reason,
                as_json=as_json,
            )
            raise SystemExit(1)
        if row.source_class != "machine_ingest":
            emit_error(
                f"Source '{source_key}' cannot be enqueued (source_class={row.source_class!r}).",
                command="ingest.enqueue",
                error_code="SOURCE_NOT_RUNNABLE",
                next_action="Only sources with source_class='machine_ingest' can be enqueued.",
                source_key=source_key,
                source_class=row.source_class,
                as_json=as_json,
            )
            raise SystemExit(1)
    # Enqueue via the in-process ingestion queue and run immediately.
    # In a production deployment, replace InProcessIngestionQueue with a
    # Celery/ARQ task queue; the interface (enqueue/get_status) stays the same.
    from app.workers.ingestion_queue import get_ingestion_queue

    queue = get_ingestion_queue()
    job_id = queue.enqueue(source_key)
    job = queue.run_job(job_id)  # run synchronously in this process

    from app.workers.ingestion_queue import JobState
    if job is None or job.state == JobState.FAILED:
        error_msg = (job.error if job else "Job not found after enqueue")
        emit_error(
            error_msg or "Ingestion job failed.",
            command="ingest.enqueue",
            error_code="JOB_FAILED",
            next_action=f"Check logs. Use 'judgectl ingest job-status {job_id}' for details.",
            source_key=source_key,
            job_id=job_id,
            as_json=as_json,
        )
        raise SystemExit(1)

    emit(
        {
            "source_key": source_key,
            "job_id": job_id,
            "run_id": job.run_id,
            "state": job.state.value,
            "records_fetched": job.records_fetched,
            "review_items": job.review_items,
            "created_records": job.created_records,
            "raw_snapshot_preserved": job.raw_snapshot_preserved,
        },
        ok=True,
        command="ingest.enqueue",
        as_json=as_json,
    )


@ingest.command("run")
@click.argument("source_key")
@click.option("--limit", default=None, type=int, help="Max items to ingest.")
@click.option("--sync", is_flag=True, default=True, help="Run synchronously (default; use for local debug).")
@click.pass_context
def ingest_run(ctx: click.Context, source_key: str, limit: int | None, sync: bool) -> None:
    """Run ingestion for SOURCE_KEY (synchronous by default; use --sync for local debug)."""
    # Lightweight registry-control import — no adapter chain triggered here.
    from app.ingestion.source_registry_ctl import check_ingestion_allowed

    as_json: bool = ctx.obj.get("as_json", False)

    with get_db_session() as db:
        row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if row is None:
            emit_error(
                f"Source '{source_key}' not found.",
                command="ingest.run",
                error_code="SOURCE_NOT_FOUND",
                next_action="Run 'judgectl sources list' to see available sources.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)

        if row.source_class != "machine_ingest":
            emit_error(
                f"Source '{source_key}' cannot be run directly (source_class={row.source_class!r}).",
                command="ingest.run",
                error_code="SOURCE_NOT_RUNNABLE",
                next_action="Only sources with source_class='machine_ingest' can be run via judgectl.",
                source_key=source_key,
                source_class=row.source_class,
                as_json=as_json,
            )
            raise SystemExit(1)

        allowed, reason = check_ingestion_allowed(row)
        if not allowed:
            emit_error(
                reason,
                command="ingest.run",
                error_code="SOURCE_NOT_RUNNABLE",
                next_action=(
                    f"Enable the source first: judgectl sources enable {source_key} --yes"
                ),
                source_key=source_key,
                source_class=row.source_class,
                as_json=as_json,
            )
            raise SystemExit(1)

        # All gates passed — now safe to import heavy adapter deps (may pull in bs4, etc.)
        from app.core.config import get_settings
        from app.ingestion.source_adapter_factory import build_adapter
        from app.ingestion.source_runner import persist_ingestion_result

        settings = get_settings()
        adapter = build_adapter(row, settings)
        if adapter is None:
            emit_error(
                f"No adapter registered for source '{source_key}'.",
                command="ingest.run",
                error_code="NO_ADAPTER",
                next_action="Verify the source's parser field in the source registry.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)

        run = IngestionRun(
            source_name=source_key,
            started_at=datetime.now(timezone.utc),
            status=RUNNING,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        try:
            result = adapter.run()
            persist_ingestion_result(db=db, source=row, run_record=run, result=result)
        except Exception as exc:
            from app.ingestion.statuses import FAILED

            run.status = FAILED
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            emit_error(
                str(exc),
                command="ingest.run",
                error_code="RUN_FAILED",
                next_action=(
                    f"Check logs. Use 'judgectl ingest status {run_id}' for details."
                ),
                source_key=source_key,
                run_id=run_id,
                as_json=as_json,
            )
            raise SystemExit(1)

        db.refresh(run)
        emit(
            {
                "run_id": run_id,
                "source_key": source_key,
                "status": run.status,
                "persisted_count": run.persisted_count,
                "error_count": run.error_count,
            },
            ok=True,
            command="ingest.run",
            as_json=as_json,
        )


@ingest.command("job-status")
@click.argument("job_id")
@click.pass_context
def ingest_job_status(ctx: click.Context, job_id: str) -> None:
    """Show status for an enqueued job by JOB_ID (UUID from ingest enqueue)."""
    as_json: bool = ctx.obj.get("as_json", False)
    from app.workers.ingestion_queue import get_ingestion_queue

    queue = get_ingestion_queue()
    job = queue.get_status(job_id)
    if job is None:
        emit_error(
            f"Job '{job_id}' not found in queue history.",
            command="ingest.job-status",
            error_code="JOB_NOT_FOUND",
            next_action="Jobs are held in-memory; they are lost on process restart.",
            job_id=job_id,
            as_json=as_json,
        )
        raise SystemExit(1)
    emit(job.to_dict(), ok=True, command="ingest.job-status", as_json=as_json)


@ingest.command("status")
@click.argument("run_id", type=int)
@click.pass_context
def ingest_status(ctx: click.Context, run_id: int) -> None:
    """Show status for ingestion run RUN_ID (from the database)."""
    as_json: bool = ctx.obj.get("as_json", False)

    with get_db_session() as db:
        run = db.query(IngestionRun).filter_by(id=run_id).first()

    if run is None:
        emit_error(
            f"Run {run_id} not found.",
            command="ingest.status",
            error_code="RUN_NOT_FOUND",
            next_action="Verify the run_id is correct.",
            run_id=run_id,
            as_json=as_json,
        )
        raise SystemExit(1)

    data = {
        "run_id": run.id,
        "source_name": run.source_name,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "fetched_count": run.fetched_count,
        "parsed_count": run.parsed_count,
        "persisted_count": run.persisted_count,
        "skipped_count": run.skipped_count,
        "error_count": run.error_count,
        "pipeline_stage": run.pipeline_stage,
        "quarantine_reason": run.quarantine_reason,
    }
    emit(data, ok=True, command="ingest.status", as_json=as_json)


# ---------------------------------------------------------------------------
# Canada-first ingest: canlii-sk
# ---------------------------------------------------------------------------

_CANLII_SK_SOURCE_KEYS = [
    SK_COURTS_QB_DECISIONS,
    SK_COURTS_CA_DECISIONS,
]


@ingest.command("canlii-sk")
@click.option(
    "--source-key",
    type=click.Choice(_CANLII_SK_SOURCE_KEYS),
    default=None,
    help="Optional single SK source key; when omitted both SK sources are processed.",
)
@click.option("--limit", default=10, show_default=True, type=int, help="Max records to fetch per database.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Fetch and parse but do NOT write to DB.")
@click.option("--commit", "do_commit", is_flag=True, default=False, help="Write parsed records to DB as pending-review.")
@click.pass_context
def ingest_canlii_sk(
    ctx: click.Context,
    source_key: str | None,
    limit: int,
    dry_run: bool,
    do_commit: bool,
) -> None:
    """Ingest Saskatchewan court decisions from the CanLII API.

    Requires JTA_CANLII_API_KEY to be set; exits clearly when absent.

    One of --dry-run or --commit is required.

    --dry-run    Fetches and parses records but writes nothing to the DB.
    --commit     Creates pending-review ReviewItem records in the DB.

    Example::

        judgectl --json ingest canlii-sk --limit 10 --dry-run
        judgectl --json ingest canlii-sk --limit 10 --commit
    """
    as_json: bool = ctx.obj.get("as_json", False)

    if not dry_run and not do_commit:
        emit_error(
            "Specify --dry-run (preview only) or --commit (write to DB).",
            command="ingest.canlii-sk",
            error_code="MODE_REQUIRED",
            next_action="Use --dry-run to preview without writing, or --commit to persist.",
            as_json=as_json,
        )
        raise SystemExit(1)

    from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

    settings = get_settings()
    api_key = settings.canlii_api_key

    if not api_key:
        emit_error(
            "CANLII_API_KEY is not configured. "
            "Register at https://www.canlii.org/en/info/api.html and set "
            "JTA_CANLII_API_KEY in your environment.",
            command="ingest.canlii-sk",
            error_code="MISSING_API_KEY",
            next_action="Set JTA_CANLII_API_KEY and retry.",
            as_json=as_json,
        )
        raise SystemExit(1)

    # Collect results across both SK court databases
    all_results: list[dict] = []
    errors: list[str] = []

    source_keys_attempted = [source_key] if source_key else _CANLII_SK_SOURCE_KEYS

    for source_key in source_keys_attempted:
        adapter = CanLIIApiAdapter(
            source_key=source_key,
            base_url="https://api.canlii.org/v1",
            api_key=api_key,
            result_count=min(limit, 100),
        )
        result = adapter.run()
        if result.errors:
            errors.extend(result.errors)
        all_results.append(
            {
                "source_key": source_key,
                "fetched": result.records_fetched,
                "review_items": len(result.review_items),
                "errors": result.errors,
                "raw_snapshot_preserved": result.raw_snapshot_bytes is not None,
                "parser_version": "canlii_api_v1",
            }
        )

        if do_commit and result.review_items:
            with get_db_session() as db:
                source_row = (
                    db.query(SourceRegistry)
                    .filter_by(source_key=source_key)
                    .first()
                )
                if source_row is None:
                    emit_error(
                        f"Source key '{source_key}' is not registered in the SourceRegistry. "
                        "Run migrations and seed the source registry before committing.",
                        command="ingest.canlii-sk",
                        error_code="SOURCE_NOT_FOUND",
                        next_action=(
                            "Ensure alembic upgrade head and source registry seed "
                            f"have been run and that '{source_key}' is present."
                        ),
                        as_json=as_json,
                    )
                    raise SystemExit(1)

                run = IngestionRun(
                    source_name=source_key,
                    started_at=datetime.now(timezone.utc),
                    status=RUNNING,
                )
                db.add(run)
                db.commit()
                db.refresh(run)

                from app.ingestion.source_runner import persist_ingestion_result

                try:
                    persist_ingestion_result(
                        db=db, source=source_row, run_record=run, result=result
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{source_key}: persist failed: {exc}")
                    from app.ingestion.statuses import FAILED
                    run.status = FAILED
                    run.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    # Fail fast: if persistence fails, stop processing further sources
                    emit_error(
                        f"Persistence failed for source '{source_key}': {exc}",
                        command="ingest.canlii-sk",
                        error_code="PERSIST_ERROR",
                        next_action="Check database connectivity and source configuration.",
                        as_json=as_json,
                    )
                    raise SystemExit(1)

    mode = "dry_run" if dry_run else "committed"
    total_fetched = sum(r["fetched"] for r in all_results)
    total_items = sum(r["review_items"] for r in all_results)

    output = {
        "mode": mode,
        "sources": all_results,
        "total_fetched": total_fetched,
        "total_review_items": total_items,
        "errors": errors,
        "parser_version": "canlii_api_v1",
        "visibility_default": "pending_review",
        "public_by_default": False,
    }

    emit(
        output,
        ok=(len(errors) == 0),
        command="ingest.canlii-sk",
        as_json=as_json,
    )

    if errors:
        raise SystemExit(1)

