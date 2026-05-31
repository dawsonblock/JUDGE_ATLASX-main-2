"""Add source_status to source_registry.

Revision ID: 20260521_0001
Revises: 20260520_0005
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260521_0001"
down_revision = "20260520_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column(
            "source_status",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "source_status")
