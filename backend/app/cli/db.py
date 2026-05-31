"""Database session access for CLI commands."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and ensure it is closed on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
