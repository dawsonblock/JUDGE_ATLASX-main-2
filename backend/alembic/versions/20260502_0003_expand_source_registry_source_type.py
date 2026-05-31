"""Expand source_registry.source_type length.

Revision ID: 20260502_0003
Revises: 20260502_0002
Create Date: 2026-05-02

Expands source_type column from String(20) to String(80) to accommodate
longer source type strings like "official_police_media".
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_0003"
down_revision: Union[str, None] = "20260502_0002"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Expand source_type column."""
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=20),
            type_=sa.String(length=80),
            existing_nullable=False,
            existing_server_default="unknown",
        )


def downgrade() -> None:
    """Revert source_type column to String(20)."""
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=80),
            type_=sa.String(length=20),
            existing_nullable=False,
            existing_server_default="unknown",
        )
