"""PostgreSQL advisory lock helpers for cross-replica ingestion coordination.

Usage pattern::

    with advisory_lock(db, INGESTION_LOCK_KEY) as acquired:
        if not acquired:
            return  # another replica holds the lock

Advisory locks are session-scoped in PostgreSQL: the lock is held for the
duration of the database connection and released automatically when the
connection closes (or by an explicit pg_advisory_unlock call).

SQLite fallback: advisory lock calls are no-ops that always report success, so
the process-local threading.Lock in runner.py remains the sole guard in
test/dev environments that use SQLite.
"""

from contextlib import contextmanager

from sqlalchemy.orm import Session

# Stable 63-bit lock key for CourtListener ingestion.
# Computed once at import time to avoid re-hashing on every call.
INGESTION_LOCK_KEY: int = abs(hash("jta:courtlistener_ingestion")) % (2**63)


def _is_sqlite(db: Session) -> bool:
    """Return True when the session is backed by a SQLite engine."""
    url = db.get_bind().engine.url  # type: ignore[union-attr]
    return str(url).startswith("sqlite")


def pg_try_advisory_lock(db: Session, key: int) -> bool:
    """Attempt to acquire a PostgreSQL session-level advisory lock.

    Returns True if the lock was acquired, False if already held by another
    session.  Always returns True for SQLite connections (no-op).
    """
    if _is_sqlite(db):
        return True
    # Use text() to avoid import-time dependency on sqlalchemy.sql
    from sqlalchemy import text  # noqa: PLC0415

    row = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).fetchone()
    return bool(row[0]) if row else False


def pg_advisory_unlock(db: Session, key: int) -> None:
    """Release a previously acquired PostgreSQL session-level advisory lock.

    No-op for SQLite connections.
    """
    if _is_sqlite(db):
        return
    from sqlalchemy import text  # noqa: PLC0415

    db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


@contextmanager
def advisory_lock(db: Session, key: int):
    """Context manager that acquires an advisory lock and yields a bool.

    Yields ``True`` if the lock was acquired, ``False`` if another holder
    already owns it.  The lock is released in the ``finally`` block only when
    it was acquired.

    Example::

        with advisory_lock(db, INGESTION_LOCK_KEY) as acquired:
            if not acquired:
                return early_return_value
            ... do work ...
    """
    acquired = pg_try_advisory_lock(db, key)
    try:
        yield acquired
    finally:
        if acquired:
            pg_advisory_unlock(db, key)
