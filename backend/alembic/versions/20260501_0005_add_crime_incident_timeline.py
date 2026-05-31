"""Add CrimeIncident timeline fields

Revision ID: 20260501_0005
Revises: 20260501_0004
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260501_0005'
down_revision: Union[str, Sequence[str], None] = '20260501_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timeline fields to crime_incidents table."""
    with op.batch_alter_table('crime_incidents') as batch_op:
        batch_op.add_column(sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('disposition', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('linked_case_ids', sa.JSON(), nullable=True))
        batch_op.create_index(op.f('ix_crime_incidents_cleared_at'), ['cleared_at'], unique=False)
        batch_op.create_index(op.f('ix_crime_incidents_disposition'), ['disposition'], unique=False)


def downgrade() -> None:
    """Remove timeline fields from crime_incidents table."""
    with op.batch_alter_table('crime_incidents') as batch_op:
        batch_op.drop_index(op.f('ix_crime_incidents_disposition'))
        batch_op.drop_index(op.f('ix_crime_incidents_cleared_at'))
        batch_op.drop_column('linked_case_ids')
        batch_op.drop_column('disposition')
        batch_op.drop_column('cleared_at')
