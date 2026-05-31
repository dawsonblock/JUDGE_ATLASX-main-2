"""Add claim sensitivity and elevated approval fields for Phase 4

Add claim sensitivity classification and elevated approval fields to memory_claims
for named-person criminal allegation publication policy.

Revision ID: 20260519_0005
Revises: 20260519_0004
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260519_0005'
down_revision = '20260519_0004'
branch_labels = None
depends_on = None


def upgrade():
    # Add claim sensitivity field
    op.add_column(
        'memory_claims',
        sa.Column('claim_sensitivity', sa.String(80), nullable=True, index=True)
    )
    
    # Add elevated approval fields
    op.add_column(
        'memory_claims',
        sa.Column('elevated_review_status', sa.String(20), nullable=True, index=True)
    )
    op.add_column(
        'memory_claims',
        sa.Column('elevated_reviewer_id', sa.String(120), nullable=True)
    )
    op.add_column(
        'memory_claims',
        sa.Column('elevated_reviewed_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    # Reverse changes
    op.drop_column('memory_claims', 'elevated_reviewed_at')
    op.drop_column('memory_claims', 'elevated_reviewer_id')
    op.drop_column('memory_claims', 'elevated_review_status')
    op.drop_column('memory_claims', 'claim_sensitivity')
