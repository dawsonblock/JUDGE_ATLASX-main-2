"""Fix SourceRegistry.is_active server default to false.

Revision ID: 20260502_0004
Revises: 20260502_0003
Create Date: 2026-05-02

Changes server_default of source_registry.is_active from true to false
so that newly-inserted rows are inactive until explicitly enabled.
Existing rows are NOT modified — operator must explicitly enable sources.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_0004"
down_revision: Union[str, None] = "20260502_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            server_default=sa.text("false"),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_registry") as batch_op:
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            server_default=sa.text("true"),
            existing_nullable=False,
        )
