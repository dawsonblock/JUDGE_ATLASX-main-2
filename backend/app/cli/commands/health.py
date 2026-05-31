"""judgectl health — quick DB + source registry ping."""

from __future__ import annotations

import click

from app.cli.db import get_db_session
from app.cli.output import emit, emit_error
from app.models.entities import SourceRegistry


@click.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Ping the database and report source registry count."""
    as_json: bool = ctx.obj.get("as_json", False)
    try:
        with get_db_session() as db:
            count = db.query(SourceRegistry).count()
        data = {"status": "ok", "source_registry_count": count}
        emit(data, ok=True, command="health", as_json=as_json)
    except Exception as exc:
        emit_error(
            str(exc),
            command="health",
            error_code="DB_UNAVAILABLE",
            next_action="Verify DATABASE_URL and that migrations have been run.",
            as_json=as_json,
        )
        raise SystemExit(1)
