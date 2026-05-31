"""Add source_tier_conflicts table.

Revision ID: 20260504_0002
Revises: 20260504_0001
Create Date: 2026-05-04

Creates the ``source_tier_conflicts`` audit table.  Every time the
conflict-resolution service suppresses or accepts an incoming value it
writes a row here so that operators can audit trust-tier enforcement
decisions after the fact.

Columns
-------
- incoming_source_id    FK → source_registry.id (lower-trust source)
- authoritative_source_id FK → source_registry.id (higher-trust source)
- entity_type           model being written (e.g. "crime_incident")
- entity_id             PK of the affected row (nullable before insert)
- field_name            model field that conflicted
- existing_value        TEXT snapshot of the existing value
- incoming_value        TEXT snapshot of the rejected (or accepted) value
- resolution            "kept_existing" | "accepted_incoming" | "merged"
- resolution_reason     human-readable explanation
- created_at / updated_at via TimestampMixin equivalents
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_0002"
down_revision: Union[str, None] = "20260504_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_tier_conflicts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incoming_source_id", sa.Integer(), nullable=False),
        sa.Column("authoritative_source_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(120), nullable=False),
        sa.Column("existing_value", sa.Text(), nullable=True),
        sa.Column("incoming_value", sa.Text(), nullable=True),
        sa.Column(
            "resolution",
            sa.String(20),
            nullable=False,
            server_default="kept_existing",
        ),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incoming_source_id"],
            ["source_registry.id"],
            name="fk_stc_incoming_source",
        ),
        sa.ForeignKeyConstraint(
            ["authoritative_source_id"],
            ["source_registry.id"],
            name="fk_stc_authoritative_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_tier_conflicts_incoming_source_id",
        "source_tier_conflicts",
        ["incoming_source_id"],
    )
    op.create_index(
        "ix_source_tier_conflicts_authoritative_source_id",
        "source_tier_conflicts",
        ["authoritative_source_id"],
    )
    op.create_index(
        "ix_source_tier_conflicts_entity_type",
        "source_tier_conflicts",
        ["entity_type"],
    )
    op.create_index(
        "ix_source_tier_conflicts_entity_id",
        "source_tier_conflicts",
        ["entity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_tier_conflicts_entity_id", table_name="source_tier_conflicts"
    )
    op.drop_index(
        "ix_source_tier_conflicts_entity_type", table_name="source_tier_conflicts"
    )
    op.drop_index(
        "ix_source_tier_conflicts_authoritative_source_id",
        table_name="source_tier_conflicts",
    )
    op.drop_index(
        "ix_source_tier_conflicts_incoming_source_id",
        table_name="source_tier_conflicts",
    )
    op.drop_table("source_tier_conflicts")
