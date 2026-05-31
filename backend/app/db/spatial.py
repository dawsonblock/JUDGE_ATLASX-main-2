from sqlalchemy import text
from sqlalchemy.engine import Engine


def initialize_postgis(engine: Engine) -> None:
    """Initialize PostGIS extension. Schema changes are managed by Alembic."""
    if engine.dialect.name != "postgresql":
        return
    # Only create PostGIS extension - all other schema changes managed by Alembic
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

