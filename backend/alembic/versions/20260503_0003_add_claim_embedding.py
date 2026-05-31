"""Add claim_embedding column to memory_claims.

Revision ID: 20260503_0003
Revises: 20260503_0002
Create Date: 2026-05-03

Adds a nullable JSON column ``claim_embedding`` to the ``memory_claims``
table to store dense float-vector embeddings produced by the
``app.services.embeddings`` module when ``JTA_EMBEDDINGS_ENABLED=true``.

Using JSON (rather than a native vector type) keeps the schema compatible
with both SQLite (tests) and PostgreSQL (production) without requiring
the pgvector extension.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260503_0003"
down_revision: Union[str, None] = "20260503_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory_claims",
        sa.Column("claim_embedding", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("memory_claims", "claim_embedding")
