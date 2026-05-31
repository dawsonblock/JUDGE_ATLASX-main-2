from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.api.routes.live_map import _apply_public_filters, get_live_map_events
from app.schemas.geo_legal_event import GeoLegalEvent


def _event(
    *,
    event_id: str,
    review_status: str,
    publish_status: str,
    confidence: float = 0.9,
    metadata: dict | None = None,
) -> GeoLegalEvent:
    return GeoLegalEvent(
        id=event_id,
        event_type="court_event",
        title="Event",
        jurisdiction="federal",
        country="Canada",
        confidence=confidence,
        confidence_label="high",
        review_status=review_status,
        publish_status=publish_status,
        source_ids=["source-1"],
        evidence_ids=["evidence-1"],
        claim_ids=["claim-1"],
        metadata_json=metadata or {},
    )


def test_public_live_map_endpoint_has_no_admin_mode_parameter() -> None:
    params = inspect.signature(get_live_map_events).parameters
    assert "admin_mode" not in params


def test_public_filter_excludes_pending_and_rejected_records() -> None:
    settings = SimpleNamespace(public_map_min_confidence=0.7)
    events = [
        _event(
            event_id="approved",
            review_status="approved",
            publish_status="public_safe",
        ),
        _event(
            event_id="pending",
            review_status="needs_review",
            publish_status="public_safe",
        ),
        _event(
            event_id="rejected",
            review_status="rejected",
            publish_status="public_safe",
        ),
    ]

    filtered = _apply_public_filters(events, settings)
    assert [item.id for item in filtered] == ["approved"]


def test_public_filter_excludes_internal_evidence_only_records() -> None:
    settings = SimpleNamespace(public_map_min_confidence=0.7)
    events = [
        _event(
            event_id="public",
            review_status="approved",
            publish_status="public_safe",
        ),
        _event(
            event_id="internal",
            review_status="approved",
            publish_status="admin_only",
        ),
    ]

    filtered = _apply_public_filters(events, settings)
    assert [item.id for item in filtered] == ["public"]


def test_public_filter_excludes_unsafe_precise_coordinates() -> None:
    settings = SimpleNamespace(public_map_min_confidence=0.7)
    events = [
        _event(
            event_id="safe",
            review_status="approved",
            publish_status="public_safe",
            metadata={"precision": "city_centroid"},
        ),
        _event(
            event_id="unsafe",
            review_status="approved",
            publish_status="public_safe",
            metadata={"precision": "exact_address"},
        ),
    ]

    filtered = _apply_public_filters(events, settings)
    assert [item.id for item in filtered] == ["safe"]
