"""add memory claim lifecycle fields

Revision ID: 20260502_0007
Revises: 20260502_0006
Create Date: 2026-05-02 00:07:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260502_0007"
down_revision = "20260502_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_claims",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "memory_claims",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_memory_claims_status", "memory_claims", ["status"])


def downgrade() -> None:
    op.drop_index("ix_memory_claims_status", table_name="memory_claims")
    op.drop_column("memory_claims", "last_seen_at")
    op.drop_column("memory_claims", "status")
