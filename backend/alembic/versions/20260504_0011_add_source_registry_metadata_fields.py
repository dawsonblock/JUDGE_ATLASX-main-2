"""add source registry metadata fields

Revision ID: 0011_sr_metadata
Revises: 0010_add_source_snapshot_id
Create Date: 2026-05-04 00:11:00.000000

Adds Canada/Saskatchewan-first source registry metadata fields:
  jurisdiction, category, priority, enabled_default,
  public_record_authority, base_url, allowed_domains,
  refresh_interval_minutes, parser, creates,
  public_publish_default, terms_url

All new columns are either nullable or carry server defaults so that
existing rows remain valid without a data migration.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260504_0011"
down_revision = "20260504_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("jurisdiction", sa.String(120), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("category", sa.String(80), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "enabled_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "public_record_authority",
            sa.String(80),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column("base_url", sa.String(2048), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("allowed_domains", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("refresh_interval_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("parser", sa.String(120), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column("creates", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_registry",
        sa.Column(
            "public_publish_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "source_registry",
        sa.Column("terms_url", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_registry", "terms_url")
    op.drop_column("source_registry", "public_publish_default")
    op.drop_column("source_registry", "creates")
    op.drop_column("source_registry", "parser")
    op.drop_column("source_registry", "refresh_interval_minutes")
    op.drop_column("source_registry", "allowed_domains")
    op.drop_column("source_registry", "base_url")
    op.drop_column("source_registry", "public_record_authority")
    op.drop_column("source_registry", "enabled_default")
    op.drop_column("source_registry", "priority")
    op.drop_column("source_registry", "category")
    op.drop_column("source_registry", "jurisdiction")
