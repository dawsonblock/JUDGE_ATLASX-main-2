"""Add snapshot integrity fields to source_snapshots table.

Revision ID: 20260502_0001
Revises: 20260501_0009
Create Date: 2026-05-02

Adds evidence integrity fields:
- original_content_hash: hash of full original content (never truncated)
- stored_content_hash: hash of what is actually stored
- content_size_bytes: size of original content in bytes
- stored_size_bytes: size of what is actually stored in bytes
- is_truncated: MUST always be False after a successful write
- extractor_name: name of the extractor used
- extractor_version: version of the extractor used
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260502_0001"
down_revision: Union[str, None] = "20260501_0009"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add evidence integrity fields to source_snapshots."""
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.add_column(sa.Column("original_content_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("stored_content_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("content_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("stored_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_truncated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("extractor_name", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("extractor_version", sa.String(40), nullable=True))


def downgrade() -> None:
    """Remove evidence integrity fields from source_snapshots."""
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.drop_column("extractor_version")
        batch_op.drop_column("extractor_name")
        batch_op.drop_column("is_truncated")
        batch_op.drop_column("stored_size_bytes")
        batch_op.drop_column("content_size_bytes")
        batch_op.drop_column("stored_content_hash")
        batch_op.drop_column("original_content_hash")
