"""Add legal_correlations table.

Adds a table for storing legal correlation hypotheses detected by the
correlation engine. Correlations are hypotheses that require review
before being used in publication decisions.

Revision ID: 20260520_0005
Revises: 20260520_0004
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260520_0005'
down_revision = '20260520_0004'
branch_labels = None
depends_on = None


def upgrade():
    # Create legal_correlations table
    op.create_table(
        'legal_correlations',
        sa.Column('id', sa.String(64), nullable=False),
        sa.Column('correlation_type', sa.String(80), nullable=False),
        sa.Column('event_ids', sa.JSON(), nullable=True),
        sa.Column('claim_ids', sa.JSON(), nullable=True),
        sa.Column('evidence_ids', sa.JSON(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=False),
        sa.Column('review_status', sa.String(20), nullable=False, server_default='needs_review'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for common query patterns
    op.create_index('idx_legal_correlations_type', 'legal_correlations', ['correlation_type'])
    op.create_index('idx_legal_correlations_review_status', 'legal_correlations', ['review_status'])
    op.create_index('idx_legal_correlations_risk_level', 'legal_correlations', ['risk_level'])
    op.create_index('idx_legal_correlations_confidence', 'legal_correlations', ['confidence'])
    op.create_index('idx_legal_correlations_type_review', 'legal_correlations', ['correlation_type', 'review_status'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_legal_correlations_type_review', table_name='legal_correlations')
    op.drop_index('idx_legal_correlations_confidence', table_name='legal_correlations')
    op.drop_index('idx_legal_correlations_risk_level', table_name='legal_correlations')
    op.drop_index('idx_legal_correlations_review_status', table_name='legal_correlations')
    op.drop_index('idx_legal_correlations_type', table_name='legal_correlations')
    
    # Drop table
    op.drop_table('legal_correlations')