"""Data contract for a single crawled web page.

This dataclass is the handoff type between the crawlee adapters and any
downstream consumer (e.g. the extraction pipeline or a review queue).  It is
intentionally plain Python — no ORM or Pydantic dependencies — so it can be
instantiated and tested without a running database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CrawledPage:
    """Immutable snapshot of a single HTTP response from a crawl.

    Invariants
    ----------
    - ``url`` is the final resolved URL after any redirects.
    - ``source_snapshot_id`` is the primary key of the persisted
      ``SourceSnapshot``; it is ``None`` only before the snapshot has been
      flushed to the database.
    - Either ``html`` or ``text`` (or both) should be non-empty for a
      successful fetch; both may be ``None`` for error responses.
    """

    url: str
    """Final resolved URL (post-redirect)."""

    source_snapshot_id: int | None
    """PK of the persisted SourceSnapshot, or None if not yet written."""

    fetched_at: datetime
    """UTC timestamp when the page was fetched."""

    html: str | None = field(default=None)
    """Raw HTML content of the response body, if available."""

    text: str | None = field(default=None)
    """Extracted plain text of the response body, if available."""

    http_status: int | None = field(default=None)
    """HTTP response status code (e.g. 200, 404)."""

    content_type: str | None = field(default=None)
    """Content-Type header value from the HTTP response."""
