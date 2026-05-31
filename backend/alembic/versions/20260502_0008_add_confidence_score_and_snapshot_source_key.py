"""add confidence_score to canonical_entities and source_key to source_snapshots

Revision ID: 20260502_0008
Revises: 20260502_0007
Create Date: 2026-05-02 00:08:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260502_0008"
down_revision = "20260502_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "canonical_entities",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "source_snapshots",
        sa.Column("source_key", sa.String(100), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("source_snapshots", "source_key")
    op.drop_column("canonical_entities", "confidence_score")
