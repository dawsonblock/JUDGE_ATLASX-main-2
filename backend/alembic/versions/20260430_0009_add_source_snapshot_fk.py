"""Add source_snapshot_id foreign key to review_items.

Revision ID: 20260430_0009
Revises: 20260430_0008
Create Date: 2026-04-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260430_0009"
down_revision: Union[str, None] = "20260430_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch alter for SQLite compatibility
    # SQLite cannot add columns with inline FK constraints; add column then create FK separately
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_snapshot_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_review_items_source_snapshot_id",
            "source_snapshots",
            ["source_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_review_items_source_snapshot_id",
            ["source_snapshot_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.drop_index("ix_review_items_source_snapshot_id")
        batch_op.drop_constraint("fk_review_items_source_snapshot_id", type_="foreignkey")
        batch_op.drop_column("source_snapshot_id")
