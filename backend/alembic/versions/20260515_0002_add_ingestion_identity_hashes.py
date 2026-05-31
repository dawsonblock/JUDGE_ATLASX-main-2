"""add ingestion identity hashes

Revision ID: 20260515_0002
Revises: 20260515_0001
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0002"
down_revision = "20260515_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crime_incidents",
        sa.Column("ingestion_identity_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "review_items",
        sa.Column("ingestion_identity_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_crime_incidents_ingestion_identity_hash",
        "crime_incidents",
        ["ingestion_identity_hash"],
        unique=False,
    )
    op.create_index(
        "ix_review_items_ingestion_identity_hash",
        "review_items",
        ["ingestion_identity_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_review_items_ingestion_identity_hash", table_name="review_items")
    op.drop_index(
        "ix_crime_incidents_ingestion_identity_hash",
        table_name="crime_incidents",
    )
    op.drop_column("review_items", "ingestion_identity_hash")
    op.drop_column("crime_incidents", "ingestion_identity_hash")
