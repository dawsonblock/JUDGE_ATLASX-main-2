"""Claim evidence links - Phase 4

Add missing fields to memory_evidence_links table:
- support_type (enum: supports, contradicts, mentions, context, supersedes)
- quote_text (evidence quote)
- char_start (character offset)
- char_end (character offset)
- page_number (source page)
- confidence (evidence confidence)

Revision ID: 20260517_0002
Revises: 20260517_0001
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260517_0002'
down_revision = '20260517_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to memory_evidence_links table
    op.add_column('memory_evidence_links', sa.Column('support_type', sa.String(20), nullable=True))
    op.add_column('memory_evidence_links', sa.Column('quote_text', sa.Text(), nullable=True))
    op.add_column('memory_evidence_links', sa.Column('char_start', sa.Integer(), nullable=True))
    op.add_column('memory_evidence_links', sa.Column('char_end', sa.Integer(), nullable=True))
    op.add_column('memory_evidence_links', sa.Column('page_number', sa.Integer(), nullable=True))
    op.add_column('memory_evidence_links', sa.Column('confidence', sa.Float(), nullable=False, server_default='0.0'))
    
    # Add CHECK constraints (PostgreSQL only; SQLite doesn't support ALTER TABLE ADD CONSTRAINT)
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.execute(
            "ALTER TABLE memory_evidence_links "
            "ADD CONSTRAINT chk_memory_evidence_links_support_type "
            "CHECK (support_type IN ('supports', 'contradicts', 'mentions', 'context', 'supersedes', NULL))"
        )
        
        # Add CHECK constraint for confidence range
        op.execute(
            "ALTER TABLE memory_evidence_links "
            "ADD CONSTRAINT chk_memory_evidence_links_confidence_range "
            "CHECK (confidence >= 0.0 AND confidence <= 1.0)"
        )


def downgrade():
    # Remove CHECK constraints (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.execute("ALTER TABLE memory_evidence_links DROP CONSTRAINT IF EXISTS chk_memory_evidence_links_confidence_range")
        op.execute("ALTER TABLE memory_evidence_links DROP CONSTRAINT IF EXISTS chk_memory_evidence_links_support_type")
    
    # Remove columns
    op.drop_column('memory_evidence_links', 'confidence')
    op.drop_column('memory_evidence_links', 'page_number')
    op.drop_column('memory_evidence_links', 'char_end')
    op.drop_column('memory_evidence_links', 'char_start')
    op.drop_column('memory_evidence_links', 'quote_text')
    op.drop_column('memory_evidence_links', 'support_type')
