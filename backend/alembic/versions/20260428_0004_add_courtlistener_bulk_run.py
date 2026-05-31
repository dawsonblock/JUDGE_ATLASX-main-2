"""add courtlistener_bulk_runs table

Revision ID: 20260428_0004
Revises: 20260428_0003
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_0004"
down_revision = "20260428_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courtlistener_bulk_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("snapshot_date", sa.String(20), nullable=False),
        sa.Column("file_name", sa.String(120), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("rows_read", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "rows_persisted", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "rows_skipped", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("errors", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "snapshot_date", "file_name", name="uq_cl_bulk_run"
        ),
    )
    op.create_index(
        "ix_cl_bulk_runs_snapshot_date",
        "courtlistener_bulk_runs",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_cl_bulk_runs_status",
        "courtlistener_bulk_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("courtlistener_bulk_runs")
