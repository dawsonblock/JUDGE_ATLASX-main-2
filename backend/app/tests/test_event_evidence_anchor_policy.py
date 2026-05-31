"""Phase 2 regression — event evidence anchor policy.

evidence_anchor_status() for an Event must only return True when the linked
source is BOTH in a public review status AND has public visibility set.
An unreviewed or private source must not anchor an event as evidence-ready.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.policies.publication_policy import (
    PUBLIC_REVIEW_STATUSES,
    evidence_anchor_status,
)

_DB = MagicMock()  # unused by the "event" branch; satisfies the db argument


def _make_event_with_source(
    *,
    source_url: str | None = "https://example.com/source",
    source_url_hash: str | None = "abc123",
    source_review_status: str = "pending_review",
    source_public_visibility: bool = False,
) -> MagicMock:
    """Build a mock Event with one source_link whose .source reflects the given params."""
    source = MagicMock()
    source.url = source_url
    source.url_hash = source_url_hash
    source.review_status = source_review_status
    # entity_public_visibility reads .is_public when the attribute exists (MagicMock
    # always auto-creates attributes, so explicitly set the value that the policy reads).
    source.is_public = source_public_visibility
    source.public_visibility = source_public_visibility

    link = MagicMock()
    link.source = source

    event = MagicMock()
    event.source_links = [link]
    return event


class TestEventEvidenceAnchorPolicy:
    def test_unreviewed_private_source_does_not_anchor(self) -> None:
        event = _make_event_with_source(
            source_review_status="pending_review",
            source_public_visibility=False,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False
        assert "event_missing_public_reviewed_source_link" in reasons

    def test_reviewed_but_private_source_does_not_anchor(self) -> None:
        reviewed_status = next(iter(PUBLIC_REVIEW_STATUSES))
        event = _make_event_with_source(
            source_review_status=reviewed_status,
            source_public_visibility=False,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False
        assert "event_missing_public_reviewed_source_link" in reasons

    def test_public_but_unreviewed_source_does_not_anchor(self) -> None:
        event = _make_event_with_source(
            source_review_status="pending_review",
            source_public_visibility=True,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False
        assert "event_missing_public_reviewed_source_link" in reasons

    def test_reviewed_and_public_source_anchors_event(self) -> None:
        reviewed_status = next(iter(PUBLIC_REVIEW_STATUSES))
        event = _make_event_with_source(
            source_review_status=reviewed_status,
            source_public_visibility=True,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is True
        assert reasons == []

    def test_no_source_links_does_not_anchor(self) -> None:
        event = MagicMock()
        event.source_links = []
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False
        assert "event_missing_public_reviewed_source_link" in reasons

    def test_source_missing_url_does_not_anchor(self) -> None:
        reviewed_status = next(iter(PUBLIC_REVIEW_STATUSES))
        event = _make_event_with_source(
            source_url=None,
            source_review_status=reviewed_status,
            source_public_visibility=True,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False

    def test_source_missing_url_hash_does_not_anchor(self) -> None:
        reviewed_status = next(iter(PUBLIC_REVIEW_STATUSES))
        event = _make_event_with_source(
            source_url_hash=None,
            source_review_status=reviewed_status,
            source_public_visibility=True,
        )
        ok, reasons = evidence_anchor_status(_DB, "event", event)
        assert ok is False
