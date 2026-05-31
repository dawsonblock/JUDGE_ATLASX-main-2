"""Ingestion queue jobs table - Phase 6

Add ingestion_queue_jobs table for durable job processing with retry logic:
- id (primary key)
- job_id (unique identifier)
- source_key (source identifier)
- state (pending, running, completed, failed)
- enqueued_at (timestamp)
- started_at (timestamp, nullable)
- finished_at (timestamp, nullable)
- run_id (FK to ingestion_runs, nullable)
- records_fetched (count)
- review_items (count)
- created_records (count)
- raw_snapshot_preserved (boolean)
- error (text, nullable)
- result (JSON, nullable)
- retry_count (integer, nullable)
- retry_after (float timestamp, nullable)

Revision ID: 20260519_0001
Revises: 20260518_0001
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260519_0001'
down_revision = '20260518_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Create ingestion_queue_jobs table
    op.create_table(
        'ingestion_queue_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(64), nullable=False),
        sa.Column('source_key', sa.String(120), nullable=False),
        sa.Column('state', sa.String(80), nullable=False, server_default='pending'),
        sa.Column('enqueued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('records_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('review_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_records', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_snapshot_preserved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('result', postgresql.JSON(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('retry_after', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['ingestion_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ingestion_queue_jobs_job_id'), 'ingestion_queue_jobs', ['job_id'], unique=True)
    op.create_index(op.f('ix_ingestion_queue_jobs_source_key'), 'ingestion_queue_jobs', ['source_key'])
    op.create_index(op.f('ix_ingestion_queue_jobs_state'), 'ingestion_queue_jobs', ['state'])


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_ingestion_queue_jobs_state'), table_name='ingestion_queue_jobs')
    op.drop_index(op.f('ix_ingestion_queue_jobs_source_key'), table_name='ingestion_queue_jobs')
    op.drop_index(op.f('ix_ingestion_queue_jobs_job_id'), table_name='ingestion_queue_jobs')
    
    # Drop table
    op.drop_table('ingestion_queue_jobs')
