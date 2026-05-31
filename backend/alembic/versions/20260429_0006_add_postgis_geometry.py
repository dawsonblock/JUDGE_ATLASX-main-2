"""Add PostGIS geometry column to locations table.

Revision ID: 20260429_0006
Revises: 20260428_0005
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260429_0006"
down_revision = "20260428_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only add geometry column on PostgreSQL (PostGIS)
    # SQLite and other databases don't support PostGIS
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        from geoalchemy2 import Geometry
        op.add_column(
            "locations",
            sa.Column(
                "geom",
                Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
                nullable=True,
            ),
        )

        # Backfill geom from existing latitude/longitude
        op.execute("""
            UPDATE locations
            SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            WHERE latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND latitude != 0.0
              AND longitude != 0.0
        """)


def downgrade() -> None:
    # Only drop if on PostgreSQL
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.drop_column("locations", "geom")
