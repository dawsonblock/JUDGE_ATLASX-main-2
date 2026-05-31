"""Add geo_legal_events table for normalized map-facing event layer

Add a normalized table that materializes events from evidence-backed claims,
legal events, crime incidents, legislation updates, and review items into one
public/admin map format.

Revision ID: 20260520_0001
Revises: 20260519_0005
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260520_0001'
down_revision = '20260519_0005'
branch_labels = None
depends_on = None


def upgrade():
    # Create geo_legal_events table
    op.create_table(
        'geo_legal_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('event_type', sa.String(80), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('lat', sa.Float, nullable=True),
        sa.Column('lng', sa.Float, nullable=True),
        sa.Column('location_name', sa.String(255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('jurisdiction', sa.String(80), nullable=False),
        sa.Column('province', sa.String(80), nullable=True),
        sa.Column('country', sa.String(80), nullable=False),
        sa.Column('source_ids', sa.JSON, nullable=True),
        sa.Column('evidence_ids', sa.JSON, nullable=True),
        sa.Column('claim_ids', sa.JSON, nullable=True),
        sa.Column('confidence', sa.Float, nullable=False, server_default='0'),
        sa.Column('confidence_label', sa.String(20), nullable=False),
        sa.Column('review_status', sa.String(20), nullable=False, index=True),
        sa.Column('publish_status', sa.String(20), nullable=False, index=True),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for common query patterns
    op.create_index('idx_geo_legal_events_event_type', 'geo_legal_events', ['event_type'])
    op.create_index('idx_geo_legal_events_review_status', 'geo_legal_events', ['review_status'])
    op.create_index('idx_geo_legal_events_publish_status', 'geo_legal_events', ['publish_status'])
    op.create_index('idx_geo_legal_events_jurisdiction', 'geo_legal_events', ['jurisdiction'])
    op.create_index('idx_geo_legal_events_country', 'geo_legal_events', ['country'])
    op.create_index('idx_geo_legal_events_created_at', 'geo_legal_events', ['created_at'])
    
    # Create composite indexes for common filter combinations
    op.create_index('idx_geo_legal_events_type_review_publish', 'geo_legal_events', ['event_type', 'review_status', 'publish_status'])
    op.create_index('idx_geo_legal_events_review_publish', 'geo_legal_events', ['review_status', 'publish_status'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_geo_legal_events_review_publish', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_type_review_publish', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_created_at', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_country', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_jurisdiction', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_publish_status', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_review_status', table_name='geo_legal_events')
    op.drop_index('idx_geo_legal_events_event_type', table_name='geo_legal_events')
    op.drop_index('ix_geo_legal_events_occurred_at', table_name='geo_legal_events')
    op.drop_index('ix_geo_legal_events_review_publish_status', table_name='geo_legal_events')
    op.drop_index('ix_geo_legal_events_confidence', table_name='geo_legal_events')
    op.drop_index('ix_geo_legal_events_jurisdiction_province', table_name='geo_legal_events')
    op.drop_index('ix_geo_legal_events_lat_lng', table_name='geo_legal_events')

    # Drop table
    op.drop_table('geo_legal_events')
