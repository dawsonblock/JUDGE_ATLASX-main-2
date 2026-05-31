"""Update queue fields for Phase 3 hardening - Phase 14

Add additional production-grade fields to ingestion_queue_jobs:
- lease_expires_at: When the worker lease expires
- dead_lettered_at: When job was moved to dead-letter queue
- last_heartbeat_at: Last heartbeat timestamp from worker

Revision ID: 20260519_0004
Revises: 20260519_0003
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260519_0004'
down_revision = '20260519_0003'
branch_labels = None
depends_on = None


def upgrade():
    # Add new fields to ingestion_queue_jobs (works for both SQLite and PostgreSQL)
    op.add_column('ingestion_queue_jobs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ingestion_queue_jobs', sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Reverse changes to ingestion_queue_jobs
    op.drop_column('ingestion_queue_jobs', 'last_heartbeat_at')
    op.drop_column('ingestion_queue_jobs', 'lease_expires_at')
