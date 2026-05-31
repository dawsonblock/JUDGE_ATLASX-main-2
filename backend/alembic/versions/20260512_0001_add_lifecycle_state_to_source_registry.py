"""Add lifecycle_state, canonical_replacement_key, status_reason,
operator_next_step to source_registry.

Revision ID: 20260512_0001
Revises: 20260511_0001
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260512_0001"
down_revision = "20260511_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("lifecycle_state", sa.String(40), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("canonical_replacement_key", sa.String(100), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("status_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("operator_next_step", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "operator_next_step")
    op.drop_column("source_registry", "status_reason")
    op.drop_column("source_registry", "canonical_replacement_key")
    op.drop_column("source_registry", "lifecycle_state")
