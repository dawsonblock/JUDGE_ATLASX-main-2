from __future__ import annotations

from app.policies.public_status import (
    PUBLIC_ADMIN_ONLY,
    PUBLIC_BLOCKED,
    PUBLIC_PRIVATE,
    PUBLIC_REDACTED,
    PUBLIC_SAFE,
    PUBLIC_VISIBLE_STATUSES,
)
from app.schemas.geo_legal_event import GeoLegalEvent


def _event_with_status(*, publish_status: str, review_status: str = "approved") -> GeoLegalEvent:
    return GeoLegalEvent(
        id=f"evt-{publish_status}",
        event_type="court_event",
        title="Status Contract Event",
        jurisdiction="federal",
        country="Canada",
        confidence=0.9,
        confidence_label="high",
        review_status=review_status,
        publish_status=publish_status,
        source_ids=["src-1"],
        evidence_ids=["ev-1"],
        claim_ids=["claim-1"],
        metadata_json={},
    )


def test_public_visible_statuses_include_safe_and_redacted() -> None:
    assert PUBLIC_SAFE in PUBLIC_VISIBLE_STATUSES
    assert PUBLIC_REDACTED in PUBLIC_VISIBLE_STATUSES


def test_non_public_statuses_not_marked_visible() -> None:
    assert PUBLIC_PRIVATE not in PUBLIC_VISIBLE_STATUSES
    assert PUBLIC_ADMIN_ONLY not in PUBLIC_VISIBLE_STATUSES
    assert PUBLIC_BLOCKED not in PUBLIC_VISIBLE_STATUSES


def test_geo_legal_event_accepts_canonical_public_statuses() -> None:
    for status in [
        PUBLIC_PRIVATE,
        PUBLIC_ADMIN_ONLY,
        PUBLIC_SAFE,
        PUBLIC_REDACTED,
        PUBLIC_BLOCKED,
    ]:
        event = _event_with_status(publish_status=status)
        assert event.publish_status == status


def test_geo_legal_event_rejects_legacy_published_status() -> None:
    try:
        _event_with_status(publish_status="published")
    except ValueError as exc:
        assert "Invalid publish_status" in str(exc)
    else:
        raise AssertionError("Expected ValueError for legacy publish_status='published'")
