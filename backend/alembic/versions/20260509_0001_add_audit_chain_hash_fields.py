"""Add entry_hash and previous_entry_hash to audit_logs for persisted chain integrity.

Revision ID: 20260509_0001
Revises: 20260508_0001_add_automation_status_to_source_registry
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0001"
down_revision = "20260508_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("previous_entry_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("entry_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "entry_hash")
    op.drop_column("audit_logs", "previous_entry_hash")
