"""Add source registry table for source management and health tracking.

Revision ID: 20260430_0008
Revises: 20260430_0007
Create Date: 2026-04-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260430_0008"
down_revision: Union[str, None] = "20260430_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False, unique=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(80), nullable=True),
        sa.Column("province_state", sa.String(80), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("license", sa.String(50), nullable=True),
        sa.Column("license_url", sa.String(2048), nullable=True),
        sa.Column(
            "fetch_method",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "update_cadence",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("fields_supported", sa.Text(), nullable=True),
        sa.Column(
            "precision_level",
            sa.String(20),
            nullable=False,
            server_default="city_centroid",
        ),
        sa.Column(
            "auto_publish_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "requires_manual_review",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("parser_version", sa.String(20), nullable=True),
        sa.Column(
            "last_successful_fetch", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        "ix_source_registry_source_key", "source_registry", ["source_key"]
    )
    op.create_index(
        "ix_source_registry_country", "source_registry", ["country"]
    )
    op.create_index(
        "ix_source_registry_source_type", "source_registry", ["source_type"]
    )
    op.create_index(
        "ix_source_registry_is_active", "source_registry", ["is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_registry_is_active")
    op.drop_index("ix_source_registry_source_type")
    op.drop_index("ix_source_registry_country")
    op.drop_index("ix_source_registry_source_key")
    op.drop_table("source_registry")

