"""Add relationship_evidence table

Revision ID: 20260501_0001
Revises: 20260430_0009
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0001"
down_revision: Union[str, None] = "20260430_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create relationship_evidence table with indexes."""
    op.create_table(
        "relationship_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_entity_type", sa.String(length=50), nullable=False),
        sa.Column("from_entity_id", sa.Integer(), nullable=False),
        sa.Column("to_entity_type", sa.String(length=50), nullable=False),
        sa.Column("to_entity_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("evidence_source", sa.String(length=120), nullable=False),
        sa.Column("evidence_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("evidence_location", sa.String(length=255), nullable=True),
        sa.Column("extracted_by", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified_by", sa.String(length=120), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["source_snapshots.id"],
            name="fk_rel_evidence_snapshot",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        "ix_rel_evidence_from_entity_type",
        "relationship_evidence",
        ["from_entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_from_entity_id",
        "relationship_evidence",
        ["from_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_to_entity_type",
        "relationship_evidence",
        ["to_entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_to_entity_id",
        "relationship_evidence",
        ["to_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_relationship_type",
        "relationship_evidence",
        ["relationship_type"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_evidence_source",
        "relationship_evidence",
        ["evidence_source"],
        unique=False,
    )
    op.create_index(
        "ix_rel_evidence_snapshot_id",
        "relationship_evidence",
        ["evidence_snapshot_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop relationship_evidence table and indexes."""
    op.drop_index("ix_rel_evidence_snapshot_id", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_evidence_source", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_relationship_type", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_to_entity_id", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_to_entity_type", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_from_entity_id", table_name="relationship_evidence")
    op.drop_index("ix_rel_evidence_from_entity_type", table_name="relationship_evidence")
    op.drop_table("relationship_evidence")
