"""Add crime aggregate statistics table for staged StatsCan ingestion.

Revision ID: 20260521_0002
Revises: 20260521_0001
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260521_0002"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crime_aggregate_statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("aggregate_key", sa.String(length=255), nullable=False),
        sa.Column("period", sa.String(length=64), nullable=True),
        sa.Column("geography", sa.String(length=255), nullable=True),
        sa.Column("statistic_name", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=120), nullable=True),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["source_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", "aggregate_key", name="uq_crime_aggregate_source_key"),
    )
    op.create_index("ix_crime_aggregate_statistics_source_key", "crime_aggregate_statistics", ["source_key"], unique=False)
    op.create_index("ix_crime_aggregate_statistics_period", "crime_aggregate_statistics", ["period"], unique=False)
    op.create_index("ix_crime_aggregate_statistics_geography", "crime_aggregate_statistics", ["geography"], unique=False)
    op.create_index("ix_crime_aggregate_statistics_source_snapshot_id", "crime_aggregate_statistics", ["source_snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_crime_aggregate_statistics_source_snapshot_id", table_name="crime_aggregate_statistics")
    op.drop_index("ix_crime_aggregate_statistics_geography", table_name="crime_aggregate_statistics")
    op.drop_index("ix_crime_aggregate_statistics_period", table_name="crime_aggregate_statistics")
    op.drop_index("ix_crime_aggregate_statistics_source_key", table_name="crime_aggregate_statistics")
    op.drop_table("crime_aggregate_statistics")
