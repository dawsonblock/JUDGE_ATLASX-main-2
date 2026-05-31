"""Add source registry operational fields

Revision ID: 20260501_0003
Revises: 20260501_0002
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260501_0003'
down_revision: Union[str, Sequence[str], None] = '20260501_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add operational fields to source_registry table."""
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('source_registry') as batch_op:
        batch_op.add_column(sa.Column('rate_limit_rpm', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_ingested_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('health_score', sa.Float(), nullable=False, server_default='1.0'))
        batch_op.add_column(sa.Column('admin_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove operational fields from source_registry table."""
    with op.batch_alter_table('source_registry') as batch_op:
        batch_op.drop_column('admin_notes')
        batch_op.drop_column('health_score')
        batch_op.drop_column('last_ingested_at')
        batch_op.drop_column('rate_limit_rpm')
