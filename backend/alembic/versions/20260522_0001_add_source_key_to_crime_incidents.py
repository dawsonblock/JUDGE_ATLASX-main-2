"""Add source_key and unique constraint to crime_incidents

Revision ID: 20260522_0001
Revises: 20260521_0002
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260522_0001"
down_revision = "20260521_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add source_key column
    op.add_column(
        "crime_incidents",
        sa.Column("source_key", sa.String(length=100), nullable=True)
    )
    # 2. Create index on source_key
    op.create_index(
        op.f("ix_crime_incidents_source_key"),
        "crime_incidents",
        ["source_key"],
        unique=False
    )
    # 3. Create unique constraint (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_unique_constraint(
            "uq_crime_incident_sourcekey_external",
            "crime_incidents",
            ["source_key", "external_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    # 1. Drop unique constraint (PostgreSQL only)
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "uq_crime_incident_sourcekey_external",
            "crime_incidents",
            type_="unique"
        )
    # 2. Drop index
    op.drop_index(
        op.f("ix_crime_incidents_source_key"),
        table_name="crime_incidents"
    )
    # 3. Drop column
    op.drop_column("crime_incidents", "source_key")
