"""add ai_correctness_checks and ai_correctness_findings tables

Revision ID: 20260428_0003
Revises: add_boundaries_table
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_0003"
down_revision = "add_boundaries_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_correctness_checks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_type", sa.String(80), nullable=False),
        sa.Column("record_id", sa.Integer, nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("event_type_supported", sa.Boolean, nullable=False),
        sa.Column("date_supported", sa.Boolean, nullable=False),
        sa.Column("location_supported", sa.Boolean, nullable=False),
        sa.Column("status_supported", sa.Boolean, nullable=False),
        sa.Column("source_supports_claim", sa.Boolean, nullable=False),
        sa.Column(
            "duplicate_candidate",
            sa.Boolean,
            nullable=False,
            server_default="0",
        ),
        sa.Column("possible_duplicate_ids", sa.JSON, nullable=True),
        sa.Column(
            "privacy_risk",
            sa.String(20),
            nullable=False,
            server_default="low",
        ),
        sa.Column("map_quality", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("result_json", sa.JSON, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ai_correctness_checks_record_type",
        "ai_correctness_checks",
        ["record_type"],
    )
    op.create_index(
        "ix_ai_correctness_checks_record_id",
        "ai_correctness_checks",
        ["record_id"],
    )
    op.create_index(
        "ix_ai_correctness_checks_map_quality",
        "ai_correctness_checks",
        ["map_quality"],
    )
    op.create_index(
        "ix_ai_correctness_checks_privacy_risk",
        "ai_correctness_checks",
        ["privacy_risk"],
    )
    op.create_index(
        "ix_ai_correctness_checks_duplicate_candidate",
        "ai_correctness_checks",
        ["duplicate_candidate"],
    )

    op.create_table(
        "ai_correctness_findings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "check_id",
            sa.Integer,
            sa.ForeignKey("ai_correctness_checks.id"),
            nullable=False,
        ),
        sa.Column("finding_type", sa.String(80), nullable=False),
        sa.Column("field_name", sa.String(80), nullable=True),
        sa.Column("expected", sa.Text, nullable=True),
        sa.Column("found", sa.Text, nullable=True),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default="info",
        ),
        sa.Column("note", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_ai_correctness_findings_check_id",
        "ai_correctness_findings",
        ["check_id"],
    )
    op.create_index(
        "ix_ai_correctness_findings_finding_type",
        "ai_correctness_findings",
        ["finding_type"],
    )


def downgrade() -> None:
    op.drop_table("ai_correctness_findings")
    op.drop_table("ai_correctness_checks")
