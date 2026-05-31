"""Add geocode_cache_id foreign key to locations table.

Adds a foreign key column to link locations to cached geocoding results.
This enables tracking the geocoding status and quality for each location.

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260520_0003'
down_revision = '20260520_0002'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    
    # SQLite requires batch mode for altering tables with foreign keys
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('locations') as batch_op:
            batch_op.add_column(
                sa.Column('geocode_cache_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_locations_geocode_cache_id',
                'geocode_cache',
                ['geocode_cache_id'],
                ['id']
            )
            batch_op.create_index(
                'idx_locations_geocode_cache_id',
                ['geocode_cache_id']
            )
    else:
        # PostgreSQL can handle direct operations
        op.add_column(
            'locations',
            sa.Column('geocode_cache_id', sa.Integer(), nullable=True)
        )
        
        op.create_foreign_key(
            'fk_locations_geocode_cache_id',
            'locations',
            'geocode_cache',
            ['geocode_cache_id'],
            ['id']
        )
        
        op.create_index(
            'idx_locations_geocode_cache_id',
            'locations',
            ['geocode_cache_id']
        )


def downgrade():
    bind = op.get_bind()
    
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('locations') as batch_op:
            batch_op.drop_index('idx_locations_geocode_cache_id')
            batch_op.drop_constraint(
                'fk_locations_geocode_cache_id',
                type_='foreignkey'
            )
            batch_op.drop_column('geocode_cache_id')
    else:
        # PostgreSQL
        op.drop_index('idx_locations_geocode_cache_id', table_name='locations')
        
        op.drop_constraint(
            'fk_locations_geocode_cache_id',
            'locations',
            type_='foreignkey'
        )
        
        op.drop_column('locations', 'geocode_cache_id')
