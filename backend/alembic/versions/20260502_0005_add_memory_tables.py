"""Add Phase 6 Fluid Memory State Engine tables.

Revision ID: 20260502_0005
Revises: 20260502_0004
Create Date: 2026-05-02

Creates six tables for the Fluid Memory State Engine:
  memory_rebuild_runs        — tracks rebuild operations
  memory_claims              — individual extracted claims
  memory_evidence_links      — claim ↔ snapshot provenance
  memory_entity_states       — computed per-entity summaries
  memory_relationship_states — computed pairwise relationships
  memory_invalidations       — immutable invalidation audit log

No public-event or graph-edge tables are modified.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_0005"
down_revision: Union[str, None] = "20260502_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_rebuild_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "rebuild_scope", sa.String(20), nullable=False, server_default="full"
        ),
        sa.Column(
            "scope_entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "entities_processed", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("claims_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "claims_invalidated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("states_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_memory_rebuild_runs_status", "memory_rebuild_runs", ["status"])
    op.create_index(
        "ix_memory_rebuild_runs_scope_entity_id",
        "memory_rebuild_runs",
        ["scope_entity_id"],
    )

    op.create_table(
        "memory_claims",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("claim_key", sa.String(64), nullable=False, unique=True),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column("claim_value", sa.Text(), nullable=False),
        sa.Column("claim_value_json", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "source_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("source_snapshots.id"),
            nullable=True,
        ),
        sa.Column("extraction_model", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_claims_claim_key", "memory_claims", ["claim_key"], unique=True
    )
    op.create_index("ix_memory_claims_claim_type", "memory_claims", ["claim_type"])
    op.create_index("ix_memory_claims_entity_id", "memory_claims", ["entity_id"])
    op.create_index(
        "ix_memory_claims_source_snapshot_id", "memory_claims", ["source_snapshot_id"]
    )

    op.create_table(
        "memory_evidence_links",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "claim_id",
            sa.Integer(),
            sa.ForeignKey("memory_claims.id"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("source_snapshots.id"),
            nullable=False,
        ),
        sa.Column("evidence_checksum", sa.String(64), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("span_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("claim_id", "snapshot_id", name="uq_memory_evidence_link"),
    )
    op.create_index(
        "ix_memory_evidence_links_claim_id", "memory_evidence_links", ["claim_id"]
    )
    op.create_index(
        "ix_memory_evidence_links_snapshot_id", "memory_evidence_links", ["snapshot_id"]
    )

    op.create_table(
        "memory_entity_states",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state_checksum", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=True),
        sa.Column("jurisdictions", sa.JSON(), nullable=True),
        sa.Column("biography_summary", sa.Text(), nullable=True),
        sa.Column(
            "last_rebuild_run_id",
            sa.Integer(),
            sa.ForeignKey("memory_rebuild_runs.id"),
            nullable=True,
        ),
        sa.Column("rebuilt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "active_claim_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_entity_states_entity_id",
        "memory_entity_states",
        ["entity_id"],
        unique=True,
    )
    op.create_index(
        "ix_memory_entity_states_last_rebuild_run_id",
        "memory_entity_states",
        ["last_rebuild_run_id"],
    )

    op.create_table(
        "memory_relationship_states",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "source_entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Integer(),
            sa.ForeignKey("canonical_entities.id"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(80), nullable=False),
        sa.Column("state_checksum", sa.String(64), nullable=False),
        sa.Column("evidence_claim_ids", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "last_rebuild_run_id",
            sa.Integer(),
            sa.ForeignKey("memory_rebuild_runs.id"),
            nullable=True,
        ),
        sa.Column("rebuilt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_memory_relationship_state",
        ),
    )
    op.create_index(
        "ix_memory_relationship_states_source_entity_id",
        "memory_relationship_states",
        ["source_entity_id"],
    )
    op.create_index(
        "ix_memory_relationship_states_target_entity_id",
        "memory_relationship_states",
        ["target_entity_id"],
    )
    op.create_index(
        "ix_memory_relationship_states_relationship_type",
        "memory_relationship_states",
        ["relationship_type"],
    )

    op.create_table(
        "memory_invalidations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("invalidation_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column(
            "triggered_by_claim_id",
            sa.Integer(),
            sa.ForeignKey("memory_claims.id"),
            nullable=True,
        ),
        sa.Column(
            "triggered_by_rebuild_run_id",
            sa.Integer(),
            sa.ForeignKey("memory_rebuild_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_invalidations_invalidation_type",
        "memory_invalidations",
        ["invalidation_type"],
    )
    op.create_index(
        "ix_memory_invalidations_target_id", "memory_invalidations", ["target_id"]
    )
    op.create_index(
        "ix_memory_invalidations_triggered_by_claim_id",
        "memory_invalidations",
        ["triggered_by_claim_id"],
    )
    op.create_index(
        "ix_memory_invalidations_triggered_by_rebuild_run_id",
        "memory_invalidations",
        ["triggered_by_rebuild_run_id"],
    )


def downgrade() -> None:
    op.drop_table("memory_invalidations")
    op.drop_table("memory_relationship_states")
    op.drop_table("memory_entity_states")
    op.drop_table("memory_evidence_links")
    op.drop_table("memory_claims")
    op.drop_table("memory_rebuild_runs")
