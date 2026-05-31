"""Add rebuild_reason to memory_rebuild_runs and public_visibility to review_items

Revision ID: 20260502_0009
Revises: 20260502_0008
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260502_0009"
down_revision = "20260502_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_rebuild_runs",
        sa.Column("rebuild_reason", sa.String(255), nullable=True),
    )
    op.add_column(
        "review_items",
        sa.Column(
            "public_visibility",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("review_items", "public_visibility")
    op.drop_column("memory_rebuild_runs", "rebuild_reason")
