"""Chain-of-custody provenance tracking for evidence snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.ingestion.statuses import QUARANTINED

if TYPE_CHECKING:
    from app.models.entities import ChainOfCustodyLog, SourceSnapshot

# Valid action values for ChainOfCustodyLog.action
CUSTODY_ACTIONS = frozenset(
    {
        "created",
        "accessed",
        "verified",
        "failed_verification",
        "exported",
        QUARANTINED,
    }
)


def record_custody_event(
    db: Session,
    snapshot: "SourceSnapshot",
    action: str,
    *,
    actor: str = "system",
    actor_type: str = "system",
    notes: str | None = None,
) -> "ChainOfCustodyLog":
    """Append a chain-of-custody entry for *snapshot*.

    The event is flushed to the session but not committed; the caller controls
    transaction boundaries.

    Args:
        db: Active SQLAlchemy session.
        snapshot: The snapshot this event belongs to.
        action: One of the strings in :data:`CUSTODY_ACTIONS`.
        actor: Identifier of the actor performing the action (e.g. user ID or
            ``"system"`` for automated processes).
        actor_type: Classification of the actor (``"system"``, ``"user"``,
            ``"admin"``).
        notes: Optional free-text annotation.

    Returns:
        The newly created :class:`ChainOfCustodyLog` instance.
    """
    from app.models.entities import ChainOfCustodyLog  # late import avoids cycles

    hash_at_event = snapshot.original_content_hash or snapshot.content_hash or ""

    entry = ChainOfCustodyLog(
        snapshot_id=snapshot.id,
        action=action,
        actor=actor,
        actor_type=actor_type,
        hash_at_event=hash_at_event,
        notes=notes,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def build_chain_of_custody(
    snapshot_id: int,
    db: Session,
) -> "list[ChainOfCustodyLog]":
    """Return all chain-of-custody entries for *snapshot_id* in creation order.

    Args:
        snapshot_id: Primary key of the target :class:`SourceSnapshot`.
        db: Active SQLAlchemy session.

    Returns:
        List of :class:`ChainOfCustodyLog` rows, sorted ascending by
        ``created_at``.
    """
    from app.models.entities import ChainOfCustodyLog

    return (
        db.query(ChainOfCustodyLog)
        .filter(ChainOfCustodyLog.snapshot_id == snapshot_id)
        .order_by(ChainOfCustodyLog.created_at.asc())
        .all()
    )
