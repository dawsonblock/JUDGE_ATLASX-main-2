"""Add source snapshots table for content archival and provenance.

Revision ID: 20260430_0007
Revises: 20260429_0006
Create Date: 2026-04-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260430_0007"
down_revision: Union[str, None] = "20260429_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "content_hash", sa.String(64), nullable=False
        ),  # SHA256
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("headers_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "storage_backend",
            sa.String(20),
            nullable=False,
            server_default="db",
        ),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column(
            "retention_until", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for common queries
    op.create_index(
        "ix_source_snapshots_source_url", "source_snapshots", ["source_url"]
    )
    op.create_index(
        "ix_source_snapshots_content_hash", "source_snapshots", ["content_hash"]
    )
    op.create_index(
        "ix_source_snapshots_fetched_at", "source_snapshots", ["fetched_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_snapshots_fetched_at")
    op.drop_index("ix_source_snapshots_content_hash")
    op.drop_index("ix_source_snapshots_source_url")
    op.drop_table("source_snapshots")
