"""Read-only memory layer queries.

Provides stable, filtered access to MemoryClaim and MemoryEntityState
data for API and service consumers.

Does NOT import from map_record, graph edge, or public event tables.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, MemoryEntityState


def get_entity_state(entity_id: int, db: Session) -> MemoryEntityState | None:
    """Return the current MemoryEntityState for *entity_id*, or None."""
    return (
        db.query(MemoryEntityState)
        .filter(MemoryEntityState.entity_id == entity_id)
        .first()
    )


def get_active_claims(entity_id: int, db: Session) -> list[MemoryClaim]:
    """Return all active MemoryClaims for *entity_id* ordered by id."""
    return (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
            MemoryClaim.status == "active",
        )
        .order_by(MemoryClaim.id)
        .all()
    )


def list_claims(
    db: Session,
    entity_id: int | None = None,
    claim_type: str | None = None,
) -> list[MemoryClaim]:
    """Return MemoryClaims with optional filters.

    Args:
        db:         SQLAlchemy session.
        entity_id:  Filter by subject entity (optional).
        claim_type: Filter by claim type (optional).

    Returns:
        Matching MemoryClaim rows ordered by id.
    """
    q = db.query(MemoryClaim)
    if entity_id is not None:
        q = q.filter(MemoryClaim.entity_id == entity_id)
    if claim_type is not None:
        q = q.filter(MemoryClaim.claim_type == claim_type)
    return q.order_by(MemoryClaim.id).all()


def search_claims_semantic(
    text: str,
    db: Session,
    k: int | None = None,
    threshold: float | None = None,
) -> list[MemoryClaim]:
    """Return MemoryClaims semantically similar to *text*.

    Delegates to :func:`app.services.embeddings.find_similar_claims`.
    Returns an empty list when embeddings are disabled or unavailable
    so callers need no feature-flag guard.

    Args:
        text:      Free-text query (e.g. "judge sentenced defendant to 5 years").
        db:        SQLAlchemy session.
        k:         Maximum results.  Defaults to ``settings.embeddings_top_k``.
        threshold: Minimum cosine similarity.
            Defaults to ``settings.embeddings_similarity_threshold``.

    Returns:
        List of :class:`~app.models.entities.MemoryClaim` ordered by
        descending similarity.
    """
    from app.services.embeddings import find_similar_claims  # noqa: PLC0415

    return find_similar_claims(text=text, db=db, k=k, threshold=threshold)
