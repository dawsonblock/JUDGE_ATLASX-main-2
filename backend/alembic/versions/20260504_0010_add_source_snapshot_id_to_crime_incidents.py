"""Add source_snapshot_id FK to crime_incidents table.

Each CrimeIncident can now reference the SourceSnapshot that produced it,
completing the provenance chain: CSV batch → SourceSnapshot → CrimeIncident.

Revision ID: 20260504_0010
Revises: 20260504_0009
Create Date: 2026-05-04 00:10:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260504_0010"
down_revision = "20260504_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility (same pattern as 20260430_0009).
    with op.batch_alter_table("crime_incidents") as batch_op:
        batch_op.add_column(
            sa.Column("source_snapshot_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_crime_incidents_source_snapshot_id",
            "source_snapshots",
            ["source_snapshot_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_crime_incidents_source_snapshot_id",
            ["source_snapshot_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("crime_incidents") as batch_op:
        batch_op.drop_index("ix_crime_incidents_source_snapshot_id")
        batch_op.drop_constraint(
            "fk_crime_incidents_source_snapshot_id", type_="foreignkey"
        )
        batch_op.drop_column("source_snapshot_id")
