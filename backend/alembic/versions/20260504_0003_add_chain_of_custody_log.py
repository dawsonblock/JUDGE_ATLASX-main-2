"""Add chain_of_custody_logs table for evidence provenance tracking.

Revision ID: 20260504_0003
Revises: 20260504_0002
Create Date: 2026-05-04

Creates the ``chain_of_custody_logs`` table that records every access,
verification, export, or quarantine event against a SourceSnapshot.
Each row is append-only; no application code updates existing rows.

Columns
-------
- id                SERIAL primary key
- snapshot_id       FK → source_snapshots.id  CASCADE DELETE
- action            VARCHAR(80) – one of created / accessed / verified /
                    failed_verification / exported / quarantined
- actor             VARCHAR(120) default 'system'
- actor_type        VARCHAR(80)  default 'system'
- hash_at_event     VARCHAR(64)  nullable – SHA-256 of snapshot at event time
- notes             TEXT         nullable
- created_at        TIMESTAMPTZ  server_default now()

Indexes
-------
ix_chain_of_custody_logs_snapshot_id
ix_chain_of_custody_logs_action
ix_chain_of_custody_logs_created_at
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_0003"
down_revision: Union[str, Sequence[str], None] = "20260504_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chain_of_custody_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("source_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False, server_default="system"),
        sa.Column("actor_type", sa.String(80), nullable=False, server_default="system"),
        sa.Column("hash_at_event", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chain_of_custody_logs_snapshot_id",
        "chain_of_custody_logs",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_chain_of_custody_logs_action",
        "chain_of_custody_logs",
        ["action"],
    )
    op.create_index(
        "ix_chain_of_custody_logs_created_at",
        "chain_of_custody_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chain_of_custody_logs_created_at", "chain_of_custody_logs")
    op.drop_index("ix_chain_of_custody_logs_action", "chain_of_custody_logs")
    op.drop_index("ix_chain_of_custody_logs_snapshot_id", "chain_of_custody_logs")
    op.drop_table("chain_of_custody_logs")
