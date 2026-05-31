"""Add source_class column to source_registry.

Revision ID: 20260506_0001
Revises: 20260505_0001
Create Date: 2026-05-06 00:01:00.000000

Adds ``source_class`` column to ``source_registry``.

Values:
  ``portal_reference`` – URL is a human-facing portal; auto-ingest is
      blocked until the operator updates ``base_url`` to a machine-readable
      API endpoint.
  ``machine_ingest`` – URL is a machine-readable endpoint; the source can
      be scheduled or manually triggered.
  ``NULL`` – legacy rows that pre-date this column; treated as
      ``machine_ingest`` for backward compatibility.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260506_0001"
down_revision = "20260505_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("source_class", sa.String(40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "source_class")
