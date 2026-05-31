"""Tests for canonical state-model mapping helpers.

These are additive compatibility tests to support phased migration from
string-based review/public fields to typed canonical states.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.policies.publication_policy import canonical_publication_state
from app.policies.state_model import (
    ArchivePublicationStatus,
    PublicationState,
    ReviewDecision,
    ReviewQueueDecision,
    archive_publication_status_for_state,
    normalize_archive_publication_status,
    normalize_review_decision,
    normalize_review_queue_decision,
    publication_state_for_archive_status,
    publication_state_for_review_status,
)
from app.review.publication_gate import (
    PublicationBlockedError,
    assert_review_item_publication_ready,
)


def test_publication_state_pending_review() -> None:
    state = publication_state_for_review_status("pending_review", False)
    assert state == PublicationState.PENDING_REVIEW  # nosec B101


def test_publication_state_public_review_status_with_visibility_true() -> None:
    state = publication_state_for_review_status("verified_court_record", True)
    assert state == PublicationState.PUBLISHED  # nosec B101


def test_publication_state_public_review_status_with_visibility_false() -> None:
    state = publication_state_for_review_status(
        "official_police_open_data_report", False
    )
    assert state == PublicationState.APPROVED  # nosec B101


def test_publication_state_restricted_status() -> None:
    state = publication_state_for_review_status("rejected", False)
    assert state == PublicationState.RESTRICTED  # nosec B101


def test_publication_state_unknown_defaults_to_draft() -> None:
    state = publication_state_for_review_status("legacy_unknown_status", False)
    assert state == PublicationState.DRAFT  # nosec B101


def test_canonical_publication_state_bridge_for_event_shape() -> None:
    event_like = SimpleNamespace(
        review_status="verified_court_record",
        public_visibility=True,
    )
    assert (
        canonical_publication_state(event_like) == PublicationState.PUBLISHED
    )  # nosec B101


def test_canonical_publication_state_bridge_for_crime_shape() -> None:
    incident_like = SimpleNamespace(
        review_status="pending_review",
        is_public=False,
    )
    assert (
        canonical_publication_state(incident_like) == PublicationState.PENDING_REVIEW
    )  # nosec B101


def test_normalize_review_decision_accepts_enum() -> None:
    normalized = normalize_review_decision(ReviewDecision.APPROVE)
    assert normalized == ReviewDecision.APPROVE  # nosec B101


def test_normalize_review_decision_accepts_case_insensitive_string() -> None:
    normalized = normalize_review_decision("ReJeCt")
    assert normalized == ReviewDecision.REJECT  # nosec B101


def test_normalize_review_decision_unknown_returns_none() -> None:
    normalized = normalize_review_decision("escalate")
    assert normalized is None  # nosec B101


def test_normalize_archive_publication_status_accepts_string() -> None:
    normalized = normalize_archive_publication_status("PUBLIC")
    assert normalized == ArchivePublicationStatus.PUBLIC  # nosec B101


def test_normalize_archive_publication_status_unknown_returns_none() -> None:
    normalized = normalize_archive_publication_status("preview")
    assert normalized is None  # nosec B101


def test_archive_publication_status_for_state_published() -> None:
    status = archive_publication_status_for_state(PublicationState.PUBLISHED)
    assert status == ArchivePublicationStatus.PUBLIC  # nosec B101


def test_archive_publication_status_for_state_default_unpublished() -> None:
    status = archive_publication_status_for_state(PublicationState.PENDING_REVIEW)
    assert status == ArchivePublicationStatus.UNPUBLISHED  # nosec B101


def test_publication_state_for_archive_status_restricted() -> None:
    state = publication_state_for_archive_status(ArchivePublicationStatus.RESTRICTED)
    assert state == PublicationState.RESTRICTED  # nosec B101


def test_normalize_review_queue_decision_accepts_enum() -> None:
    normalized = normalize_review_queue_decision(ReviewQueueDecision.APPROVED)
    assert normalized == ReviewQueueDecision.APPROVED  # nosec B101


def test_normalize_review_queue_decision_accepts_case_insensitive_string() -> None:
    normalized = normalize_review_queue_decision("FLAGGED")
    assert normalized == ReviewQueueDecision.FLAGGED  # nosec B101


def test_normalize_review_queue_decision_unknown_returns_none() -> None:
    normalized = normalize_review_queue_decision("escalate")
    assert normalized is None  # nosec B101


def test_review_item_publication_gate_accepts_normalized_approved_status() -> None:
    item_like = SimpleNamespace(id=42, status="APPROVED", source_snapshot_id=10)
    assert_review_item_publication_ready(item_like)


def test_review_item_publication_gate_blocks_non_approved_status() -> None:
    item_like = SimpleNamespace(id=43, status="flagged", source_snapshot_id=10)
    try:
        assert_review_item_publication_ready(item_like)
        raise AssertionError("flagged review items must be blocked")
    except PublicationBlockedError:
        pass
