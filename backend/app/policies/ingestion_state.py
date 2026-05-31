"""Ingestion state enumeration and review-status mapping.

Provides:
- ``IngestionState`` — ordered enum representing a record's position in
  the ingestion-to-publication pipeline.
- ``ingestion_state_for_review_status`` — map a raw ``review_status``
  string (as stored on :class:`~app.models.entities.ReviewItem`) to the
  corresponding :class:`IngestionState`.

This module intentionally has no SQLAlchemy or runtime dependencies so
it can be imported at module load time without triggering DB connections.
"""

from __future__ import annotations

from enum import Enum

from app.policies.publication_policy import (
    CORRECTED,
    DISPUTED,
    NEWS_ONLY_CONTEXT,
    OFFICIAL_POLICE_OPEN_DATA_REPORT,
    OFFICIAL_STATISTICS_AGGREGATE,
    PENDING_REVIEW,
    REJECTED,
    REMOVED_FROM_PUBLIC,
    VERIFIED_COURT_RECORD,
)


class IngestionState(str, Enum):
    """Ordered states a record moves through from raw fetch to publication.

    Values are plain strings so they can be stored in JSON / log output
    without extra serialisation steps.
    """

    FETCHED = "fetched"
    """Raw content retrieved from source; not yet parsed or validated."""

    PENDING = "pending"
    """Parsed and awaiting human review."""

    APPROVED = "approved"
    """Reviewer approved the record; not yet publicly visible."""

    PUBLISHED = "published"
    """Publicly visible (review_status in PUBLIC_REVIEW_STATUSES,
    public_visibility=True)."""

    DISPUTED = "disputed"
    """A reviewer or subject has raised a factual dispute."""

    REJECTED = "rejected"
    """Record was rejected during review and will not be published."""

    REMOVED = "removed"
    """Previously published; subsequently removed from public view."""

    NEWS_CONTEXT = "news_context"
    """Record is sourced from news only; not eligible for public map/court
    display but may appear in news-context summaries."""

    UNKNOWN = "unknown"
    """State cannot be determined from the available review_status value."""


# ---------------------------------------------------------------------------
# Mapping from review_status strings → IngestionState
# ---------------------------------------------------------------------------

_REVIEW_STATUS_TO_STATE: dict[str, IngestionState] = {
    PENDING_REVIEW: IngestionState.PENDING,
    VERIFIED_COURT_RECORD: IngestionState.PUBLISHED,
    OFFICIAL_POLICE_OPEN_DATA_REPORT: IngestionState.PUBLISHED,
    OFFICIAL_STATISTICS_AGGREGATE: IngestionState.PUBLISHED,
    CORRECTED: IngestionState.PUBLISHED,
    NEWS_ONLY_CONTEXT: IngestionState.NEWS_CONTEXT,
    DISPUTED: IngestionState.DISPUTED,
    REJECTED: IngestionState.REJECTED,
    REMOVED_FROM_PUBLIC: IngestionState.REMOVED,
}


def ingestion_state_for_review_status(review_status: str | None) -> IngestionState:
    """Return the :class:`IngestionState` that corresponds to *review_status*.

    Args:
        review_status: The ``review_status`` string stored on a
            :class:`~app.models.entities.ReviewItem`, or ``None`` if the
            field is absent / the record has not yet been reviewed.

    Returns:
        The matching :class:`IngestionState`, or :attr:`IngestionState.UNKNOWN`
        if *review_status* is ``None`` or not recognised.
    """
    if review_status is None:
        return IngestionState.UNKNOWN
    return _REVIEW_STATUS_TO_STATE.get(review_status, IngestionState.UNKNOWN)
