"""Add boundaries table for Natural Earth administrative data.

Revision ID: add_boundaries_table
Revises: add_incident_link_tables
Create Date: 2026-04-28 00:02:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_boundaries_table"
down_revision: Union[str, Sequence[str], None] = "add_incident_link_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boundaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("iso_code", sa.String(10), nullable=True),
        sa.Column("boundary_type", sa.String(40), nullable=False),
        sa.Column("parent_iso", sa.String(10), nullable=True),
        sa.Column("source", sa.String(80), nullable=False, server_default="natural_earth"),
        sa.Column("geojson_simplified", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_boundaries_name", "boundaries", ["name"])
    op.create_index("ix_boundaries_iso_code", "boundaries", ["iso_code"])
    op.create_index("ix_boundaries_boundary_type", "boundaries", ["boundary_type"])


def downgrade() -> None:
    op.drop_index("ix_boundaries_boundary_type", table_name="boundaries")
    op.drop_index("ix_boundaries_iso_code", table_name="boundaries")
    op.drop_index("ix_boundaries_name", table_name="boundaries")
    op.drop_table("boundaries")
