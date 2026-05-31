"""Complete audit-chain hash fields: add payload_hash, before_hash, after_hash,
chain_version, and actor_auth_method to audit_logs.

Revision ID: 20260509_0002
Revises: 20260509_0001
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0002"
down_revision = "20260509_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("actor_auth_method", sa.String(80), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("payload_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("before_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("after_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("chain_version", sa.Integer(), nullable=True, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "chain_version")
    op.drop_column("audit_logs", "after_hash")
    op.drop_column("audit_logs", "before_hash")
    op.drop_column("audit_logs", "payload_hash")
    op.drop_column("audit_logs", "actor_auth_method")
