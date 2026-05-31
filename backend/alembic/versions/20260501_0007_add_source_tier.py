"""Add source_tier to SourceRegistry.

Revision ID: 20260501_0007
Revises: 20260501_0006
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0007"
down_revision: Union[str, None] = "20260501_0006"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add source_tier column to source_registry table."""
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.add_column(
            sa.Column("source_tier", sa.String(80), nullable=False, server_default="news_only_context")
        )
        batch_op.create_index("ix_source_registry_source_tier", ["source_tier"])


def downgrade() -> None:
    """Remove source_tier column from source_registry table."""
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.drop_index("ix_source_registry_source_tier")
        batch_op.drop_column("source_tier")
