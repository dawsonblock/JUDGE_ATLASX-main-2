"""Record human review decisions on ReviewItem rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.entities import LegalInstrument, ReviewItem, SourceRegistry
from app.policies.publication_policy import PENDING_REVIEW
from app.policies.state_model import (
    ReviewQueueDecision,
    normalize_review_queue_decision,
)
from sqlalchemy.orm import Session

APPROVED = ReviewQueueDecision.APPROVED.value
REJECTED = ReviewQueueDecision.REJECTED.value
FLAGGED = ReviewQueueDecision.FLAGGED.value
VALID_DECISIONS = frozenset({APPROVED, REJECTED, FLAGGED})


@dataclass
class ReviewDecisionResult:
    ok: bool
    item_id: int
    new_status: str
    reason: str | None = None


def record_decision(
    db: Session,
    item_id: int,
    *,
    decision: str,
    reviewer_id: str,
    notes: str | None = None,
) -> ReviewDecisionResult:
    """Apply *decision* to a ReviewItem and flush (caller commits).

    Returns ReviewDecisionResult with ok=False if item not found or decision invalid.
    """
    normalized_decision = normalize_review_queue_decision(decision)
    if normalized_decision is None:
        return ReviewDecisionResult(
            ok=False,
            item_id=item_id,
            new_status="",
            reason=f"invalid_decision: {decision}",
        )
    decision_value = normalized_decision.value

    item = db.query(ReviewItem).filter(ReviewItem.id == item_id).first()
    if item is None:
        return ReviewDecisionResult(
            ok=False, item_id=item_id, new_status="", reason="not_found"
        )

    item.status = decision_value
    item.reviewer_id = reviewer_id
    item.reviewer_notes = notes
    item.reviewed_at = datetime.now(timezone.utc)

    if normalized_decision == ReviewQueueDecision.APPROVED:
        # ReviewItem approval is an internal workflow decision only.  It means
        # "approved for promotion/draft/further review", not public
        # publication authority.
        item.public_visibility = False

    if item.record_type == "LegalInstrument":
        payload = item.suggested_payload_json or {}
        source_key = payload.get("source_key") or payload.get("source_name")
        if source_key is None and item.source_snapshot is not None:
            source_key = item.source_snapshot.source_key
        source = (
            db.query(SourceRegistry).filter_by(source_key=source_key).first()
            if source_key
            else None
        )
        if source is not None:
            instrument = (
                db.query(LegalInstrument)
                .filter(
                    LegalInstrument.source_id == source.id,
                    LegalInstrument.unique_id == payload.get("unique_id"),
                    LegalInstrument.language == payload.get("language"),
                )
                .first()
            )
            if instrument is not None:
                if normalized_decision == ReviewQueueDecision.APPROVED:
                    instrument.review_status = PENDING_REVIEW
                    instrument.public_visibility = "private"
                elif normalized_decision == ReviewQueueDecision.REJECTED:
                    instrument.review_status = REJECTED
                    instrument.public_visibility = "private"

    db.flush()

    return ReviewDecisionResult(ok=True, item_id=item_id, new_status=decision_value)
