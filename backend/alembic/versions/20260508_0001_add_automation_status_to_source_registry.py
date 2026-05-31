"""Add automation_status column to source_registry.

Revision ID: 20260508_0001
Revises: 20260507_0001
Create Date: 2026-05-08 00:01:00.000000

Adds ``automation_status`` (String(30), nullable) to ``source_registry``.

Intended values:
  ``machine_ready``          – adapter implemented and tested; safe to schedule.
  ``machine_ready_disabled`` – adapter implemented but disabled pending review.
  ``adapter_missing``        – no adapter written yet; manual ingestion only.
  ``experimental``           – adapter exists but not production-qualified.
  ``deprecated``             – source retired; kept for historical record.
  ``NULL``                   – legacy rows; treat as ``adapter_missing``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260508_0001"
down_revision = "20260507_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("automation_status", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "automation_status")
