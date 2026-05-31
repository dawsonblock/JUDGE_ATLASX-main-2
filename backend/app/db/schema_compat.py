# LEGACY COMPATIBILITY ONLY — do NOT call from main.py or any clean-install path.
#
# This module existed to patch databases created by the original Alembic migration
# which was missing many ORM columns.  The migration was corrected on 2025-04-28 and
# now creates the full correct schema.  This file is kept only so that pre-existing
# development databases can still be patched if needed by running it manually.
# It must not be imported or called on startup.
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


REVIEW_COLUMNS = {
    "review_status": "VARCHAR(80) DEFAULT 'pending_review' NOT NULL",
    "reviewed_at": "TIMESTAMP",
    "reviewed_by": "VARCHAR(120)",
    "review_notes": "TEXT",
    "correction_note": "TEXT",
    "dispute_note": "TEXT",
}


def ensure_prototype_schema_compat(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "legal_sources" in table_names:
            columns = {column["name"] for column in inspector.get_columns("legal_sources")}
            if "api_url" not in columns:
                connection.execute(text("ALTER TABLE legal_sources ADD COLUMN api_url TEXT"))
            _ensure_review_columns(connection, columns, "legal_sources")
            if "public_visibility" not in columns:
                connection.execute(text("ALTER TABLE legal_sources ADD COLUMN public_visibility BOOLEAN DEFAULT FALSE NOT NULL"))
        if "events" in table_names:
            columns = {column["name"] for column in inspector.get_columns("events")}
            _ensure_review_columns(connection, columns, "events")
            if "public_visibility" not in columns:
                connection.execute(text("ALTER TABLE events ADD COLUMN public_visibility BOOLEAN DEFAULT FALSE NOT NULL"))
        if "crime_incidents" in table_names:
            columns = {column["name"] for column in inspector.get_columns("crime_incidents")}
            _ensure_review_columns(connection, columns, "crime_incidents")
        if "ingestion_runs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("ingestion_runs")}
            if "persisted_count" not in columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN persisted_count INTEGER DEFAULT 0"))
            if "skipped_count" not in columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN skipped_count INTEGER DEFAULT 0"))
        if "review_items" in table_names:
            columns = {column["name"] for column in inspector.get_columns("review_items")}
            if "reviewer_notes" not in columns:
                connection.execute(text("ALTER TABLE review_items ADD COLUMN reviewer_notes TEXT"))


def _ensure_review_columns(connection, columns: set[str], table_name: str) -> None:
    for column_name, column_type in REVIEW_COLUMNS.items():
        if column_name not in columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
