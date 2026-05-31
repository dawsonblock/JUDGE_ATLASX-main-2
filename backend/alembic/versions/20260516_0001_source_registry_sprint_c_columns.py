"""Add Sprint C columns to source_registry

Adds 7 new operational/governance fields that were added to the SourceRegistry
ORM model in Sprint C but not yet migrated to the database:
  - confidence_class
  - retention_policy
  - canonical_url
  - evidence_required
  - terms_verified
  - authentication_required
  - rate_limit_policy

Revision ID: 20260516_0001
Revises: 20260515_0004
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260516_0001"
down_revision = "20260515_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("confidence_class", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("retention_policy", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "evidence_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column("terms_verified", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "authentication_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column("rate_limit_policy", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "rate_limit_policy")
    op.drop_column("source_registry", "authentication_required")
    op.drop_column("source_registry", "terms_verified")
    op.drop_column("source_registry", "evidence_required")
    op.drop_column("source_registry", "canonical_url")
    op.drop_column("source_registry", "retention_policy")
    op.drop_column("source_registry", "confidence_class")
