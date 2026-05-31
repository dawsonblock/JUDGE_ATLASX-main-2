"""judgectl sources — source registry management."""

from __future__ import annotations

from pathlib import Path

import click

from app.cli.db import get_db_session
from app.cli.output import emit, emit_error
from app.ingestion.automation_statuses import MACHINE_READY_DISABLED, MACHINE_READY_ENABLED
from app.ingestion.source_registry_ctl import can_enable_source
from app.models.entities import SourceRegistry

_PROJECT_ROOT = Path(__file__).parents[4]

# Source classes that are allowed for automated ingestion.
_RUNNABLE_CLASS = "machine_ingest"


@click.group()
def sources() -> None:
    """Source registry management."""


@sources.command("list")
@click.pass_context
def sources_list(ctx: click.Context) -> None:
    """List all registered sources."""
    as_json: bool = ctx.obj.get("as_json", False)
    with get_db_session() as db:
        rows = db.query(SourceRegistry).order_by(SourceRegistry.source_key).all()
    data = [
        {
            "source_key": r.source_key,
            "source_name": r.source_name,
            "is_active": r.is_active,
            "source_class": r.source_class,
            "health_score": r.health_score,
            "last_ingested_at": r.last_ingested_at,
        }
        for r in rows
    ]
    emit(data, ok=True, command="sources.list", as_json=as_json)


@sources.command("info")
@click.argument("source_key")
@click.pass_context
def sources_info(ctx: click.Context, source_key: str) -> None:
    """Show full details for SOURCE_KEY."""
    as_json: bool = ctx.obj.get("as_json", False)
    with get_db_session() as db:
        row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if row is None:
        emit_error(
            f"Source '{source_key}' not found.",
            command="sources.info",
            error_code="SOURCE_NOT_FOUND",
            next_action="Run 'judgectl sources list' to see available sources.",
            source_key=source_key,
            as_json=as_json,
        )
        raise SystemExit(1)
    data = {
        "source_key": row.source_key,
        "source_name": row.source_name,
        "is_active": row.is_active,
        "source_class": row.source_class,
        "source_tier": row.source_tier,
        "auto_publish_enabled": row.auto_publish_enabled,
        "requires_manual_review": row.requires_manual_review,
        "health_score": row.health_score,
        "reliability_score": row.reliability_score,
        "last_ingested_at": row.last_ingested_at,
        "last_error": row.last_error,
        "last_error_at": row.last_error_at,
        "admin_notes": row.admin_notes,
    }
    emit(data, ok=True, command="sources.info", as_json=as_json)


@sources.command("validate")
@click.pass_context
def sources_validate(ctx: click.Context) -> None:
    """Run validate_workflows.py guard against registered sources."""
    import subprocess
    import sys

    as_json: bool = ctx.obj.get("as_json", False)
    script = _PROJECT_ROOT / "scripts" / "validate_workflows.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )
    ok = result.returncode == 0
    data = {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    emit(data, ok=ok, command="sources.validate", as_json=as_json)
    if not ok:
        raise SystemExit(1)


@sources.command("enable")
@click.argument("source_key")
@click.option("--yes", is_flag=True, required=True, help="Confirm the enable action.")
@click.pass_context
def sources_enable(ctx: click.Context, source_key: str, yes: bool) -> None:
    """Enable SOURCE_KEY for automated ingestion.

    Only sources with source_class == 'machine_ingest' may be enabled.
    portal_reference, disabled_stub, and other non-runnable classes are
    rejected with SOURCE_NOT_RUNNABLE.
    """
    as_json: bool = ctx.obj.get("as_json", False)
    with get_db_session() as db:
        row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if row is None:
            emit_error(
                f"Source '{source_key}' not found.",
                command="sources.enable",
                error_code="SOURCE_NOT_FOUND",
                next_action="Run 'judgectl sources list' to see available sources.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)

        # Policy gate: only machine_ingest sources may be enabled.
        if row.source_class != _RUNNABLE_CLASS:
            emit_error(
                f"Source '{source_key}' has class '{row.source_class}' and cannot be "
                "enabled for automated ingestion.",
                command="sources.enable",
                error_code="SOURCE_NOT_RUNNABLE",
                next_action="Only machine_ingest sources can be enabled for automated ingestion.",
                source_key=source_key,
                source_class=row.source_class,
                as_json=as_json,
            )
            raise SystemExit(1)

        enable_ok, enable_blockers = can_enable_source(row)
        if not enable_ok:
            emit_error(
                f"Source '{source_key}' cannot be enabled: {'; '.join(enable_blockers)}",
                command="sources.enable",
                error_code="SOURCE_ENABLE_BLOCKED",
                next_action="Resolve lifecycle/config blockers then retry.",
                source_key=source_key,
                blockers=enable_blockers,
                as_json=as_json,
            )
            raise SystemExit(1)

        # Use same adapter/secret readiness checks as admin API.
        from app.core.config import get_settings
        from app.ingestion.source_adapter_factory import (
            build_adapter,
            missing_required_secret_for_parser,
        )

        settings = get_settings()
        missing_secret = missing_required_secret_for_parser(row.parser, settings)
        if missing_secret is not None:
            emit_error(
                f"Source '{source_key}' blocked by missing secret: {missing_secret}",
                command="sources.enable",
                error_code="SOURCE_MISSING_SECRET",
                next_action="Configure required secret and retry.",
                source_key=source_key,
                missing_secret=missing_secret,
                as_json=as_json,
            )
            raise SystemExit(1)

        if build_adapter(row, settings) is None:
            emit_error(
                f"Source '{source_key}' has no registered adapter.",
                command="sources.enable",
                error_code="SOURCE_NO_ADAPTER",
                next_action="Implement and register adapter before enabling.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)

        row.is_active = True
        row.automation_status = MACHINE_READY_ENABLED
        db.commit()
    emit(
        {"source_key": source_key, "is_active": True},
        ok=True,
        command="sources.enable",
        as_json=as_json,
    )


@sources.command("disable")
@click.argument("source_key")
@click.option("--yes", is_flag=True, required=True, help="Confirm the disable action.")
@click.pass_context
def sources_disable(ctx: click.Context, source_key: str, yes: bool) -> None:
    """Disable SOURCE_KEY (stops new ingestion runs)."""
    as_json: bool = ctx.obj.get("as_json", False)
    with get_db_session() as db:
        row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
        if row is None:
            emit_error(
                f"Source '{source_key}' not found.",
                command="sources.disable",
                error_code="SOURCE_NOT_FOUND",
                next_action="Run 'judgectl sources list' to see available sources.",
                source_key=source_key,
                as_json=as_json,
            )
            raise SystemExit(1)
        if row.automation_status == MACHINE_READY_ENABLED:
            row.automation_status = MACHINE_READY_DISABLED
        row.is_active = False
        db.commit()
    emit(
        {"source_key": source_key, "is_active": False},
        ok=True,
        command="sources.disable",
        as_json=as_json,
    )
