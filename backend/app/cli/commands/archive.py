"""judgectl archive — JSONL export and verification commands."""
from __future__ import annotations

from pathlib import Path

import click

from app.cli.output import emit, emit_error

_DEFAULT_SNAPSHOTS_OUT = "artifacts/exports/source_snapshots.jsonl"
_DEFAULT_MEMORY_OUT = "artifacts/exports/memory_claims.jsonl"


@click.group()
def archive() -> None:
    """Archive export and verification commands."""


@archive.command("export-snapshots")
@click.option(
    "--out",
    default=_DEFAULT_SNAPSHOTS_OUT,
    show_default=True,
    help="Output JSONL file path.",
)
@click.pass_context
def archive_export_snapshots(ctx: click.Context, out: str) -> None:
    """Export source snapshots to JSONL."""
    as_json: bool = ctx.obj.get("as_json", False)
    from app.archive.export_snapshots import export_snapshots_to_jsonl
    from app.cli.db import get_db_session

    out_path = Path(out)
    try:
        with get_db_session() as db:
            count = export_snapshots_to_jsonl(db, out_path)
        emit(
            {"exported": count, "path": str(out_path)},
            ok=True,
            command="archive.export-snapshots",
            as_json=as_json,
        )
    except Exception as exc:  # noqa: BLE001
        emit_error(
            str(exc),
            command="archive.export-snapshots",
            error_code="EXPORT_FAILED",
            next_action="Check database connection and output path permissions.",
            as_json=as_json,
        )
        raise SystemExit(1)


@archive.command("export-memory")
@click.option(
    "--out",
    default=_DEFAULT_MEMORY_OUT,
    show_default=True,
    help="Output JSONL file path.",
)
@click.pass_context
def archive_export_memory(ctx: click.Context, out: str) -> None:
    """Export memory claims to JSONL."""
    as_json: bool = ctx.obj.get("as_json", False)
    from app.archive.export_memory_claims import export_memory_claims_to_jsonl
    from app.cli.db import get_db_session

    out_path = Path(out)
    try:
        with get_db_session() as db:
            count = export_memory_claims_to_jsonl(db, out_path)
        emit(
            {"exported": count, "path": str(out_path)},
            ok=True,
            command="archive.export-memory",
            as_json=as_json,
        )
    except Exception as exc:  # noqa: BLE001
        emit_error(
            str(exc),
            command="archive.export-memory",
            error_code="EXPORT_FAILED",
            next_action="Check database connection and output path permissions.",
            as_json=as_json,
        )
        raise SystemExit(1)


@archive.command("verify")
@click.option(
    "--path",
    "file_path",
    required=True,
    help="Path to the JSONL file to verify.",
)
@click.pass_context
def archive_verify(ctx: click.Context, file_path: str) -> None:
    """Verify a JSONL export file for completeness and provenance."""
    as_json: bool = ctx.obj.get("as_json", False)
    from app.archive.verify_export import verify_jsonl_export

    result = verify_jsonl_export(Path(file_path))
    d = result.to_dict()
    emit(d, ok=result.ok, command="archive.verify", as_json=as_json)
    if not result.ok:
        raise SystemExit(1)
