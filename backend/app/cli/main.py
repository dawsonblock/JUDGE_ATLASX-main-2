"""Entrypoint for the judgectl CLI."""

from __future__ import annotations

import click

from app.cli.commands.archive import archive
from app.cli.commands.audit import audit
from app.cli.commands.health import health
from app.cli.commands.ingest import ingest
from app.cli.commands.sources import sources


@click.group()
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit machine-readable JSON.",
)
@click.pass_context
def main(ctx: click.Context, as_json: bool) -> None:
    """judgectl — operator CLI for JUDGE Atlas."""
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json


main.add_command(health)
main.add_command(sources)
main.add_command(ingest)
main.add_command(audit)
main.add_command(archive)
