"""Add canonical_entities and entity_source_records tables

Revision ID: 20260501_0002
Revises: 20260501_0001
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0002"
down_revision: Union[str, None] = "20260501_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create canonical_entities and entity_source_records tables."""
    # Create canonical_entities table
    op.create_table(
        "canonical_entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_id_external", sa.String(length=255), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merge_confidence", sa.Float(), nullable=False, default=1.0),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            default="active",
        ),
        sa.Column(
            "merged_into_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id", name="fk_canonical_merged_into"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for canonical_entities
    op.create_index(
        "ix_canonical_entities_entity_type",
        "canonical_entities",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_entities_status",
        "canonical_entities",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_entities_merged_into_id",
        "canonical_entities",
        ["merged_into_id"],
        unique=False,
    )

    # Create entity_source_records table
    op.create_table(
        "entity_source_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "canonical_entity_id",
            sa.Integer(),
            sa.ForeignKey(
                "canonical_entities.id", name="fk_esr_canonical_entity"
            ),
            nullable=False,
        ),
        sa.Column("source_table", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("match_confidence", sa.Float(), nullable=False, default=0.0),
        sa.Column("match_reason", sa.String(length=50), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("linked_by", sa.String(length=120), nullable=True),
        sa.Column("verified_by", sa.String(length=120), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for entity_source_records
    op.create_index(
        "ix_esr_canonical_entity_id",
        "entity_source_records",
        ["canonical_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_esr_source_name",
        "entity_source_records",
        ["source_name"],
        unique=False,
    )
    op.create_index(
        "ix_esr_source_record",
        "entity_source_records",
        ["source_table", "source_record_id"],
        unique=False,
    )

    # Create unique constraint to prevent duplicate source record links
    op.create_index(
        "ix_esr_unique_source_record",
        "entity_source_records",
        ["source_table", "source_record_id", "source_name"],
        unique=True,
    )


def downgrade() -> None:
    """Drop canonical_entities and entity_source_records tables."""
    op.drop_index("ix_esr_unique_source_record", table_name="entity_source_records")
    op.drop_index("ix_esr_source_record", table_name="entity_source_records")
    op.drop_index("ix_esr_source_name", table_name="entity_source_records")
    op.drop_index("ix_esr_canonical_entity_id", table_name="entity_source_records")
    op.drop_table("entity_source_records")

    op.drop_index("ix_canonical_entities_merged_into_id", table_name="canonical_entities")
    op.drop_index("ix_canonical_entities_status", table_name="canonical_entities")
    op.drop_index("ix_canonical_entities_entity_type", table_name="canonical_entities")
    op.drop_table("canonical_entities")
