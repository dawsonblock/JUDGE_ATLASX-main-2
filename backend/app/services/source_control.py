"""Source control gate for ingestion endpoints.

Single responsibility: raise SourceDisabledError when a source is missing
or disabled, so callers can convert it to an HTTP 403 response.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry


class SourceDisabledError(Exception):
    """Raised when a source is missing or has is_active=False."""


def require_source_enabled(db: Session, source_key: str) -> SourceRegistry:
    """Return the SourceRegistry row or raise SourceDisabledError.

    Args:
        db: Active SQLAlchemy session.
        source_key: Registry key (matches SourceRegistry.source_key).

    Returns:
        The active SourceRegistry row.

    Raises:
        SourceDisabledError: If the source is not found or is disabled.
    """
    source = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if source is None:
        raise SourceDisabledError(f"source '{source_key}' not found in registry")
    if not source.is_active:
        raise SourceDisabledError(f"source '{source_key}' is disabled")
    return source
