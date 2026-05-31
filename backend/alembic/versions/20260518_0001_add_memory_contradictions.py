"""Durable contradiction system - Phase 3

Add memory_contradictions table for persistent contradiction tracking:
- id (primary key)
- claim_a_id (FK to memory_claims)
- claim_b_id (FK to memory_claims)
- conflict_type (enum: value_conflict, temporal_overlap, identity_conflict, 
  jurisdiction_conflict, source_conflict, legal_status_conflict)
- severity (enum: low, medium, high, critical)
- status (enum: open, reviewing, resolved, false_positive, ignored)
- detected_by (system or user)
- detected_at (timestamp)
- resolved_at (timestamp, nullable)
- reviewer_id (FK to users, nullable)
- resolution_note (text, nullable)
- created_at (timestamp)
- updated_at (timestamp)

Revision ID: 20260518_0001
Revises: 20260517_0002
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260518_0001'
down_revision = '20260517_0002'
branch_labels = None
depends_on = None


def upgrade():
    # Create memory_contradictions table
    op.create_table(
        'memory_contradictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_a_id', sa.Integer(), nullable=False),
        sa.Column('claim_b_id', sa.Integer(), nullable=False),
        sa.Column('conflict_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('detected_by', sa.String(50), nullable=False, server_default='system'),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['claim_a_id'], ['memory_claims.id'], ),
        sa.ForeignKeyConstraint(['claim_b_id'], ['memory_claims.id'], ),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_memory_contradictions_claim_a_id'), 'memory_contradictions', ['claim_a_id'])
    op.create_index(op.f('ix_memory_contradictions_claim_b_id'), 'memory_contradictions', ['claim_b_id'])
    op.create_index(op.f('ix_memory_contradictions_conflict_type'), 'memory_contradictions', ['conflict_type'])
    op.create_index(op.f('ix_memory_contradictions_status'), 'memory_contradictions', ['status'])
    op.create_index(op.f('ix_memory_contradictions_severity'), 'memory_contradictions', ['severity'])
    
    # Add unique constraint (PostgreSQL only; SQLite doesn't support ALTER TABLE ADD CONSTRAINT)
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.create_unique_constraint(
            'uq_memory_contradictions_claims',
            'memory_contradictions',
            ['claim_a_id', 'claim_b_id', 'conflict_type']
        )


def downgrade():
    bind = op.get_bind()
    
    # Drop unique constraint (PostgreSQL only)
    if bind.dialect.name != 'sqlite':
        op.drop_constraint('uq_memory_contradictions_claims', 'memory_contradictions', type_='unique')
    
    # Drop indexes
    op.drop_index(op.f('ix_memory_contradictions_severity'), table_name='memory_contradictions')
    op.drop_index(op.f('ix_memory_contradictions_status'), table_name='memory_contradictions')
    op.drop_index(op.f('ix_memory_contradictions_conflict_type'), table_name='memory_contradictions')
    op.drop_index(op.f('ix_memory_contradictions_claim_b_id'), table_name='memory_contradictions')
    op.drop_index(op.f('ix_memory_contradictions_claim_a_id'), table_name='memory_contradictions')
    
    # Drop table
    op.drop_table('memory_contradictions')
