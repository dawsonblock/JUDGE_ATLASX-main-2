"""Add source_authority_weight to memory_contradictions - Phase 14

Add source_authority_weight field to memory_contradictions table for
source-authority-aware contradiction handling. This field stores the
authority weight for resolution (higher = more authoritative source).

Source authority hierarchy:
- official_court_record (weight 1.0)
- official_government (weight 0.8)
- press_release (weight 0.6)
- social_media (weight 0.4)

Revision ID: 20260519_0003
Revises: 20260519_0002
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260519_0003'
down_revision = '20260519_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('memory_contradictions', sa.Column('source_authority_weight', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('memory_contradictions', 'source_authority_weight')
