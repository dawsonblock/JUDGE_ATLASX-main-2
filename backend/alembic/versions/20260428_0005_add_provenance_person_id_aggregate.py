"""Add cl_person_id, cl_bulk_provenance table, cl_provenance JSON cols, is_aggregate.

Revision ID: 20260428_0005
Revises: 20260428_0004
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_0005"
down_revision = "20260428_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. cl_person_id on judges
    op.add_column(
        "judges",
        sa.Column("cl_person_id", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_judges_cl_person_id", "judges", ["cl_person_id"], unique=True
    )

    # 2. cl_provenance JSON columns
    op.add_column("courts", sa.Column("cl_provenance", sa.JSON(), nullable=True))
    op.add_column("cases", sa.Column("cl_provenance", sa.JSON(), nullable=True))
    op.add_column("events", sa.Column("cl_provenance", sa.JSON(), nullable=True))
    op.add_column(
        "legal_sources", sa.Column("cl_provenance", sa.JSON(), nullable=True)
    )

    # 3. is_aggregate on crime_incidents
    op.add_column(
        "crime_incidents",
        sa.Column(
            "is_aggregate", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.create_index(
        "ix_crime_incidents_is_aggregate",
        "crime_incidents",
        ["is_aggregate"],
    )

    # 4. cl_bulk_provenance table
    op.create_table(
        "cl_bulk_provenance",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("courtlistener_bulk_runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("cl_table", sa.String(80), nullable=False),
        sa.Column("cl_row_id", sa.String(80), nullable=False),
        sa.Column("source_file", sa.String(120), nullable=False),
        sa.Column("snapshot_date", sa.String(20), nullable=False),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("record_id", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id", "cl_table", "cl_row_id", name="uq_cl_bulk_provenance"
        ),
    )


def downgrade() -> None:
    op.drop_table("cl_bulk_provenance")

    op.drop_index(
        "ix_crime_incidents_is_aggregate", table_name="crime_incidents"
    )
    op.drop_column("crime_incidents", "is_aggregate")

    op.drop_column("legal_sources", "cl_provenance")
    op.drop_column("events", "cl_provenance")
    op.drop_column("cases", "cl_provenance")
    op.drop_column("courts", "cl_provenance")

    op.drop_index("ix_judges_cl_person_id", table_name="judges")
    op.drop_column("judges", "cl_person_id")
