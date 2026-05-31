"""Add ingestion_run_id to SourceSnapshot and ReviewItem.

Revision ID: 20260501_0006
Revises: 20260501_0005
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0006"
down_revision: Union[str, None] = "20260501_0005"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add ingestion_run_id columns to source_snapshots and review_items."""
    # Add to source_snapshots
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("ingestion_run_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_snapshot_ingestion_run",
            "ingestion_runs",
            ["ingestion_run_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_source_snapshots_ingestion_run_id",
            ["ingestion_run_id"],
            unique=False,
        )

    # Add to review_items
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.add_column(
            sa.Column("ingestion_run_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_review_item_ingestion_run",
            "ingestion_runs",
            ["ingestion_run_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_review_items_ingestion_run_id",
            ["ingestion_run_id"],
            unique=False,
        )


def downgrade() -> None:
    """Remove ingestion_run_id columns."""
    # Remove from review_items
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.drop_index("ix_review_items_ingestion_run_id")
        batch_op.drop_constraint("fk_review_item_ingestion_run", type_="foreignkey")
        batch_op.drop_column("ingestion_run_id")

    # Remove from source_snapshots
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.drop_index("ix_source_snapshots_ingestion_run_id")
        batch_op.drop_constraint("fk_snapshot_ingestion_run", type_="foreignkey")
        batch_op.drop_column("ingestion_run_id")
