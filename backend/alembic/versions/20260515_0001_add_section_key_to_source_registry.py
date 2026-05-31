"""Add section_key column to source_registry table.

Revision ID: 20260515_0001
Revises: 20260514_0002
Create Date: 2026-05-15 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260515_0001"
down_revision = "20260514_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("section_key", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "section_key")
