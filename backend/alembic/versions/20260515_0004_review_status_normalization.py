"""add review_status to relationship_evidence and normalize legal_instrument default

- Adds relationship_evidence.review_status (VARCHAR 50, NOT NULL, default 'pending_review').
- Backfills legal_instruments.review_status: rows where review_status = 'pending'
  (the wrong ingestion-run sentinel) are updated to 'pending_review'.

Revision ID: 20260515_0004
Revises: 20260515_0003
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260515_0004"
down_revision = "20260515_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add review_status column to relationship_evidence.
    op.add_column(
        "relationship_evidence",
        sa.Column(
            "review_status",
            sa.String(length=50),
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.create_index(
        "ix_relationship_evidence_review_status",
        "relationship_evidence",
        ["review_status"],
    )

    # 2. Backfill legal_instruments that were incorrectly seeded with the
    #    ingestion-run sentinel 'pending' instead of the publication-workflow
    #    sentinel 'pending_review'.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE legal_instruments"
            " SET review_status = 'pending_review'"
            " WHERE review_status = 'pending'"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_relationship_evidence_review_status",
        table_name="relationship_evidence",
    )
    op.drop_column("relationship_evidence", "review_status")

    # Reverse the backfill: rows that are currently 'pending_review' but
    # were originally 'pending' cannot be distinguished from rows that were
    # correctly set.  We leave them as 'pending_review' to avoid data loss.
    # This is intentional and documented in the migration history.
