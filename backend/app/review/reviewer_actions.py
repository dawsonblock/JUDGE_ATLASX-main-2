"""High-level reviewer action helpers that combine decision + audit log."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.audit.append_log import append_audit_entry
from app.review.decisions import record_decision, ReviewDecisionResult


def apply_review_decision(
    db: Session,
    item_id: int,
    *,
    decision: str,
    reviewer_id: str,
    notes: str | None = None,
    actor_ip: str | None = None,
) -> ReviewDecisionResult:
    """Record a review decision and write an audit log entry.

    Caller is responsible for committing the session.
    """
    result = record_decision(db, item_id, decision=decision, reviewer_id=reviewer_id, notes=notes)

    if result.ok:
        append_audit_entry(
            db,
            action=f"review:{decision}",
            entity_type="ReviewItem",
            entity_id=str(item_id),
            actor_id=reviewer_id,
            actor_type="reviewer",
            actor_ip=actor_ip,
            payload={"decision": decision, "notes": notes, "new_status": result.new_status},
        )

    return result
