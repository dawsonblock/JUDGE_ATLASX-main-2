"""Review lifecycle guard tests for alpha publication safety."""

from __future__ import annotations

from app.policies.state_model import PublicationState, publication_state_for_review_status


def test_pending_review_maps_to_pending_publication_state() -> None:
    assert publication_state_for_review_status("pending_review", False) == PublicationState.PENDING_REVIEW


def test_rejected_maps_to_rejected_publication_state() -> None:
    assert publication_state_for_review_status("rejected", False) == PublicationState.RESTRICTED


def test_verified_public_without_visibility_stays_internal() -> None:
    state = publication_state_for_review_status("verified_court_record", False)
    assert state == PublicationState.APPROVED
