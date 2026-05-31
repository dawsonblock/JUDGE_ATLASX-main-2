"""Add production-grade fields to ingestion queue.

Adds: locked_by, locked_at, idempotency_key, and dead letter queue table.

Revision ID: 20260519_0002
Revises: 20260519_0001
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260519_0002'
down_revision = '20260519_0001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    
    # Use batch mode for SQLite, direct operations for PostgreSQL
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('ingestion_queue_jobs') as batch_op:
            batch_op.add_column(sa.Column('locked_by', sa.String(120), nullable=True))
            batch_op.add_column(sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column('idempotency_key', sa.String(255), nullable=True))
            batch_op.create_index(op.f('ix_ingestion_queue_jobs_locked_by'), ['locked_by'])
            batch_op.create_index(op.f('ix_ingestion_queue_jobs_idempotency_key'), ['idempotency_key'])
            batch_op.create_unique_constraint(
                'uq_ingestion_queue_jobs_source_key_idempotency_key',
                ['source_key', 'idempotency_key']
            )
    else:
        op.add_column('ingestion_queue_jobs', sa.Column('locked_by', sa.String(120), nullable=True))
        op.add_column('ingestion_queue_jobs', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('ingestion_queue_jobs', sa.Column('idempotency_key', sa.String(255), nullable=True))
        
        op.create_index(op.f('ix_ingestion_queue_jobs_locked_by'), 'ingestion_queue_jobs', ['locked_by'])
        op.create_index(op.f('ix_ingestion_queue_jobs_idempotency_key'), 'ingestion_queue_jobs', ['idempotency_key'])
        
        op.create_unique_constraint(
            'uq_ingestion_queue_jobs_source_key_idempotency_key',
            'ingestion_queue_jobs',
            ['source_key', 'idempotency_key']
        )
    
    # Create dead_letter_queue_jobs table
    op.create_table(
        'dead_letter_queue_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_job_id', sa.String(64), nullable=False),
        sa.Column('source_key', sa.String(120), nullable=False),
        sa.Column('failure_reason', sa.String(255), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('original_job_data', sa.JSON() if bind.dialect.name == 'sqlite' else postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('retry_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('retry_count_at_failure', sa.Integer(), server_default='0', nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(120), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('dead_lettered_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('original_job_id', name='uq_dead_letter_queue_jobs_original_job_id')
    )
    
    op.create_index(op.f('ix_dead_letter_queue_jobs_source_key'), 'dead_letter_queue_jobs', ['source_key'])
    op.create_index(op.f('ix_dead_letter_queue_jobs_created_at'), 'dead_letter_queue_jobs', ['created_at'])


def downgrade():
    bind = op.get_bind()
    
    op.drop_index(op.f('ix_dead_letter_queue_jobs_created_at'), table_name='dead_letter_queue_jobs')
    op.drop_index(op.f('ix_dead_letter_queue_jobs_source_key'), table_name='dead_letter_queue_jobs')
    op.drop_table('dead_letter_queue_jobs')
    
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('ingestion_queue_jobs') as batch_op:
            batch_op.drop_constraint('uq_ingestion_queue_jobs_source_key_idempotency_key', type_='unique')
            batch_op.drop_index(op.f('ix_ingestion_queue_jobs_idempotency_key'))
            batch_op.drop_index(op.f('ix_ingestion_queue_jobs_locked_by'))
            batch_op.drop_column('idempotency_key')
            batch_op.drop_column('locked_at')
            batch_op.drop_column('locked_by')
    else:
        op.drop_constraint('uq_ingestion_queue_jobs_source_key_idempotency_key', 'ingestion_queue_jobs', type_='unique')
        op.drop_index(op.f('ix_ingestion_queue_jobs_idempotency_key'), table_name='ingestion_queue_jobs')
        op.drop_index(op.f('ix_ingestion_queue_jobs_locked_by'), table_name='ingestion_queue_jobs')
        op.drop_column('ingestion_queue_jobs', 'idempotency_key')
        op.drop_column('ingestion_queue_jobs', 'locked_at')
        op.drop_column('ingestion_queue_jobs', 'locked_by')
