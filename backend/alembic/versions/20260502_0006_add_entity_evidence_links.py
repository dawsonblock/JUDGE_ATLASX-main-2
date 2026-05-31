"""Add entity_evidence_links table.

Revision ID: 20260502_0006
Revises: 20260502_0005
Create Date: 2026-05-02

Links canonical entities to source snapshots so memory rebuild can scope
snapshot selection to snapshots actually relevant to the entity.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_0006"
down_revision: Union[str, None] = "20260502_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity_evidence_links",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("source_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "linking_reason",
            sa.String(80),
            nullable=False,
            server_default="ingestion_run",
        ),
        sa.UniqueConstraint("entity_id", "snapshot_id", name="uq_entity_evidence_link"),
    )
    op.create_index(
        "ix_entity_evidence_links_entity_id", "entity_evidence_links", ["entity_id"]
    )
    op.create_index(
        "ix_entity_evidence_links_snapshot_id",
        "entity_evidence_links",
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_entity_evidence_links_snapshot_id", table_name="entity_evidence_links")
    op.drop_index("ix_entity_evidence_links_entity_id", table_name="entity_evidence_links")
    op.drop_table("entity_evidence_links")
