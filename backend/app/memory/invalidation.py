"""Memory layer invalidation service.

Marks claims and entity states as inactive and writes
MemoryInvalidation audit records.

Does NOT import from map_record, graph edge, or public event tables.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import (
    EntityGraphEdge,
    MemoryClaim,
    MemoryEntityState,
    MemoryInvalidation,
)


def invalidate_claim(
    claim_id: int,
    reason: str,
    db: Session,
    rebuild_run_id: int | None = None,
) -> MemoryInvalidation:
    """Mark a MemoryClaim inactive and write an audit record.

    Returns the MemoryInvalidation row (not yet committed).
    Raises ValueError if claim_id does not exist.
    """
    claim = db.get(MemoryClaim, claim_id)
    if claim is None:
        raise ValueError(f"MemoryClaim {claim_id} does not exist")

    now = datetime.now(timezone.utc)
    claim.is_active = False
    claim.status = "inactive"
    claim.invalidated_at = now
    claim.invalidation_reason = reason

    if claim.source_snapshot_id is not None:
        edges = (
            db.query(EntityGraphEdge)
            .filter(
                EntityGraphEdge.source_snapshot_id == claim.source_snapshot_id,
                EntityGraphEdge.subject_id == claim.entity_id,
                EntityGraphEdge.status == "active",
            )
            .all()
        )
        for edge in edges:
            edge.status = "retracted"
        db.flush()

    audit = MemoryInvalidation(
        invalidation_type="claim",
        target_id=claim_id,
        reason=reason,
        triggered_by_claim_id=None,
        triggered_by_rebuild_run_id=rebuild_run_id,
        invalidated_at=now,
    )
    db.add(audit)
    return audit


def invalidate_entity_state(
    entity_id: int,
    reason: str,
    db: Session,
    rebuild_run_id: int | None = None,
) -> None:
    """Mark all active claims for *entity_id* inactive and audit each.

    Also zeroes the active_claim_count on the MemoryEntityState row.
    Raises ValueError if no MemoryEntityState exists for this entity.
    """
    state = (
        db.query(MemoryEntityState)
        .filter(MemoryEntityState.entity_id == entity_id)
        .first()
    )
    if state is None:
        raise ValueError(f"No MemoryEntityState for entity {entity_id}")

    active_claims = (
        db.query(MemoryClaim)
        .filter(MemoryClaim.entity_id == entity_id)
        .filter(MemoryClaim.is_active.is_(True))
        .all()
    )

    now = datetime.now(timezone.utc)
    for claim in active_claims:
        claim.is_active = False
        claim.status = "inactive"
        claim.invalidated_at = now
        claim.invalidation_reason = reason
        db.add(
            MemoryInvalidation(
                invalidation_type="claim",
                target_id=claim.id,
                reason=reason,
                triggered_by_claim_id=None,
                triggered_by_rebuild_run_id=rebuild_run_id,
                invalidated_at=now,
            )
        )

    state.active_claim_count = 0
    db.add(
        MemoryInvalidation(
            invalidation_type="entity_state",
            target_id=state.id,
            reason=reason,
            triggered_by_claim_id=None,
            triggered_by_rebuild_run_id=rebuild_run_id,
            invalidated_at=now,
        )
    )
