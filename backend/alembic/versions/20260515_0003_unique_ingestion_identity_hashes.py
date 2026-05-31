"""unique ingestion identity hashes

Replace the non-unique indexes on ingestion_identity_hash with partial
unique indexes (WHERE ingestion_identity_hash IS NOT NULL).  NULL values
represent records ingested before the hash was introduced and must not
participate in the uniqueness constraint.

Revision ID: 20260515_0003
Revises: 20260515_0002
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260515_0003"
down_revision = "20260515_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the non-unique indexes from 0002 before creating the partial unique ones.
    op.drop_index(
        "ix_crime_incidents_ingestion_identity_hash",
        table_name="crime_incidents",
    )
    op.drop_index(
        "ix_review_items_ingestion_identity_hash",
        table_name="review_items",
    )

    # PostgreSQL supports partial unique indexes natively.
    # SQLite (used in tests) does not support WHERE in CREATE INDEX via
    # alembic's op.create_index; a raw execute is used for SQLite compat.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # CREATE UNIQUE INDEX CONCURRENTLY cannot run inside a transaction.
        # Use regular (non-concurrent) creation here; the table is pre-production
        # alpha-scale so a brief table lock is acceptable.
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS"
                " uq_crime_incidents_ingestion_identity_hash"
                " ON crime_incidents (ingestion_identity_hash)"
                " WHERE ingestion_identity_hash IS NOT NULL"
            )
        )
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS"
                " uq_review_items_ingestion_identity_hash"
                " ON review_items (ingestion_identity_hash)"
                " WHERE ingestion_identity_hash IS NOT NULL"
            )
        )
    else:
        # SQLite / other: partial unique via WHERE clause (supported since SQLite 3.8.9)
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS"
                " uq_crime_incidents_ingestion_identity_hash"
                " ON crime_incidents (ingestion_identity_hash)"
                " WHERE ingestion_identity_hash IS NOT NULL"
            )
        )
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS"
                " uq_review_items_ingestion_identity_hash"
                " ON review_items (ingestion_identity_hash)"
                " WHERE ingestion_identity_hash IS NOT NULL"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "DROP INDEX IF EXISTS uq_crime_incidents_ingestion_identity_hash"
            )
        )
        bind.execute(
            sa.text(
                "DROP INDEX IF EXISTS uq_review_items_ingestion_identity_hash"
            )
        )
    else:
        bind.execute(
            sa.text(
                "DROP INDEX IF EXISTS uq_crime_incidents_ingestion_identity_hash"
            )
        )
        bind.execute(
            sa.text(
                "DROP INDEX IF EXISTS uq_review_items_ingestion_identity_hash"
            )
        )

    # Restore the plain non-unique indexes from 0002 so that downgrade is reversible.
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
