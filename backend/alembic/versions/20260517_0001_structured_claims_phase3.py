"""Structured claim schema - Phase 3

Add missing fields to memory_claims table for structured claims:
- claim_uid (unique identifier separate from claim_key)
- predicate (structured predicate field)
- object_entity_id (FK to canonical_entities for object claims)
- object_value (literal value for non-entity objects)
- object_value_type (enum: entity, literal, date, number, boolean)
- normalized_value (canonical representation)
- jurisdiction (jurisdiction scope)
- valid_from (temporal validity start)
- valid_to (temporal validity end)
- observed_at (when claim was observed in source)
- source_quality (source authority level)
- corroboration_count (number of supporting sources)
- contradiction_count (number of conflicting claims)
- review_status (review workflow state)
- superseded_by_claim_id (FK for claim replacement)
- extraction_run_id (FK to ingestion run)
- derived_from_ai (boolean flag)

Revision ID: 20260517_0001
Revises: 20260516_0004
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260517_0001'
down_revision = '20260516_0004'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to memory_claims table
    # SQLite-compatible: make nullable initially, populate in separate step
    op.add_column('memory_claims', sa.Column('claim_uid', sa.String(64), nullable=True))
    
    # Populate claim_uid for existing rows with unique identifiers
    # Use a batch approach to handle SQLite limitations
    connection = op.get_bind()
    
    # For PostgreSQL, use gen_random_uuid()
    # For SQLite, use a sequential approach
    if connection.dialect.name == 'postgresql':
        connection.execute(
            sa.text("UPDATE memory_claims SET claim_uid = gen_random_uuid()::text WHERE claim_uid IS NULL")
        )
    else:
        # SQLite: generate sequential UUIDs for existing rows
        result = connection.execute(sa.text("SELECT id FROM memory_claims WHERE claim_uid IS NULL ORDER BY id"))
        for row in result:
            # Generate a simple UUID-like string for SQLite
            import uuid
            connection.execute(
                sa.text("UPDATE memory_claims SET claim_uid = :uid WHERE id = :id"),
                {"uid": str(uuid.uuid4()), "id": row[0]}
            )
    
    # Now create the unique index after populating
    op.create_index(op.f('ix_memory_claims_claim_uid'), 'memory_claims', ['claim_uid'], unique=True)
    
    op.add_column('memory_claims', sa.Column('predicate', sa.String(80), nullable=True))
    op.create_index(op.f('ix_memory_claims_predicate'), 'memory_claims', ['predicate'])
    
    op.add_column('memory_claims', sa.Column('object_entity_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_memory_claims_object_entity_id'), 'memory_claims', ['object_entity_id'])
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.create_foreign_key('fk_memory_claims_object_entity_id', 'memory_claims', 'canonical_entities', ['object_entity_id'], ['id'])
    
    op.add_column('memory_claims', sa.Column('object_value', sa.Text(), nullable=True))
    op.add_column('memory_claims', sa.Column('object_value_type', sa.String(20), nullable=True))
    op.add_column('memory_claims', sa.Column('normalized_value', sa.Text(), nullable=True))
    
    op.add_column('memory_claims', sa.Column('extraction_run_id', sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.create_foreign_key('fk_memory_claims_extraction_run_id', 'memory_claims', 'ingestion_runs', ['extraction_run_id'], ['id'])
    
    op.add_column(
        'memory_claims',
        sa.Column('derived_from_ai', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    
    op.add_column('memory_claims', sa.Column('review_status', sa.String(20), nullable=False, server_default='pending_review'))
    op.create_index(op.f('ix_memory_claims_review_status'), 'memory_claims', ['review_status'])
    
    op.add_column('memory_claims', sa.Column('superseded_by_claim_id', sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.create_foreign_key('fk_memory_claims_superseded_by_claim_id', 'memory_claims', 'memory_claims', ['superseded_by_claim_id'], ['id'])
    
    op.add_column('memory_claims', sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True))
    
    op.add_column('memory_claims', sa.Column('jurisdiction', sa.String(80), nullable=True))
    op.create_index(op.f('ix_memory_claims_jurisdiction'), 'memory_claims', ['jurisdiction'])
    
    op.add_column('memory_claims', sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True))
    op.add_column('memory_claims', sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True))
    op.add_column('memory_claims', sa.Column('observed_at', sa.DateTime(timezone=True), nullable=True))
    
    op.add_column('memory_claims', sa.Column('source_quality', sa.String(80), nullable=True))
    
    op.add_column(
        'memory_claims',
        sa.Column('corroboration_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'memory_claims',
        sa.Column('contradiction_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    
    # Add CHECK constraints (PostgreSQL only; SQLite doesn't support ALTER TABLE ADD CONSTRAINT)
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.execute("ALTER TABLE memory_claims ADD CONSTRAINT chk_memory_claims_confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0)")
        op.execute("ALTER TABLE memory_claims ADD CONSTRAINT chk_memory_claims_valid_to_after_valid_from CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)")
        op.execute("ALTER TABLE memory_claims ADD CONSTRAINT chk_memory_claims_object_value_type CHECK (object_value_type IN ('entity', 'literal', 'date', 'number', 'boolean', NULL))")


def downgrade():
    # Remove CHECK constraints (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.execute("ALTER TABLE memory_claims DROP CONSTRAINT IF EXISTS chk_memory_claims_object_value_type")
        op.execute("ALTER TABLE memory_claims DROP CONSTRAINT IF EXISTS chk_memory_claims_valid_to_after_valid_from")
        op.execute("ALTER TABLE memory_claims DROP CONSTRAINT IF EXISTS chk_memory_claims_confidence_range")
    
    # Remove columns
    op.drop_column('memory_claims', 'contradiction_count')
    op.drop_column('memory_claims', 'corroboration_count')
    op.drop_column('memory_claims', 'source_quality')
    op.drop_column('memory_claims', 'observed_at')
    op.drop_column('memory_claims', 'valid_to')
    op.drop_column('memory_claims', 'valid_from')
    op.drop_index(op.f('ix_memory_claims_jurisdiction'), table_name='memory_claims')
    op.drop_column('memory_claims', 'jurisdiction')
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.drop_constraint('fk_memory_claims_superseded_by_claim_id', 'memory_claims', type_='foreignkey')
    op.drop_column('memory_claims', 'superseded_by_claim_id')
    op.drop_column('memory_claims', 'superseded_at')
    op.drop_index(op.f('ix_memory_claims_review_status'), table_name='memory_claims')
    op.drop_column('memory_claims', 'review_status')
    op.drop_column('memory_claims', 'derived_from_ai')
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.drop_constraint('fk_memory_claims_extraction_run_id', 'memory_claims', type_='foreignkey')
    op.drop_column('memory_claims', 'extraction_run_id')
    op.drop_column('memory_claims', 'normalized_value')
    op.drop_column('memory_claims', 'object_value_type')
    op.drop_column('memory_claims', 'object_value')
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.drop_constraint('fk_memory_claims_object_entity_id', 'memory_claims', type_='foreignkey')
    op.drop_index(op.f('ix_memory_claims_object_entity_id'), table_name='memory_claims')
    op.drop_column('memory_claims', 'object_entity_id')
    op.drop_index(op.f('ix_memory_claims_predicate'), table_name='memory_claims')
    op.drop_column('memory_claims', 'predicate')
    op.drop_index(op.f('ix_memory_claims_claim_uid'), table_name='memory_claims')
    op.drop_column('memory_claims', 'claim_uid')
