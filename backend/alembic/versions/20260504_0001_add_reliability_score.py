"""Add reliability_score column to source_registry.

Revision ID: 20260504_0001
Revises: 20260503_0003
Create Date: 2026-05-04

Adds a NOT NULL float column ``reliability_score`` (default 1.0) to the
``source_registry`` table.  The value is computed by
``app.services.publish_rules.compute_reliability_score`` and represents
the product of the numeric trust-tier weight and the existing
``health_score``.  A server_default of '1.0' ensures existing rows get
the safest possible starting value without a separate backfill pass.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_0001"
down_revision: Union[str, None] = "20260503_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column(
            "reliability_score",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "reliability_score")
