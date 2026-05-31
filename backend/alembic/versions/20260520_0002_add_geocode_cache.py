"""Add geocode_cache table for geocoding results.

Adds a cache table for storing geocoding lookup results to avoid
redundant API calls and ensure consistency across geocoding results.

Revision ID: 20260520_0002
Revises: 20260520_0001
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260520_0002'
down_revision = '20260520_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Create geocode_cache table
    op.create_table(
        'geocode_cache',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('query', sa.String(500), nullable=False, index=True),
        sa.Column('query_hash', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('latitude', sa.Float, nullable=True),
        sa.Column('longitude', sa.Float, nullable=True),
        sa.Column('location_name', sa.String(255), nullable=True),
        sa.Column('formatted_address', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, index=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('country', sa.String(80), nullable=True),
        sa.Column('province', sa.String(80), nullable=True),
        sa.Column('jurisdiction', sa.String(80), nullable=True),
        sa.Column('source_key', sa.String(255), nullable=True),
        sa.Column('metadata', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for common query patterns
    op.create_index('idx_geocode_cache_status', 'geocode_cache', ['status'])
    op.create_index('idx_geocode_cache_provider', 'geocode_cache', ['provider'])
    op.create_index('idx_geocode_cache_country_province', 'geocode_cache', ['country', 'province'])
    op.create_index('idx_geocode_cache_last_used_at', 'geocode_cache', ['last_used_at'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_geocode_cache_last_used_at', table_name='geocode_cache')
    op.drop_index('idx_geocode_cache_country_province', table_name='geocode_cache')
    op.drop_index('idx_geocode_cache_provider', table_name='geocode_cache')
    op.drop_index('idx_geocode_cache_status', table_name='geocode_cache')

    # Drop table
    op.drop_table('geocode_cache')
