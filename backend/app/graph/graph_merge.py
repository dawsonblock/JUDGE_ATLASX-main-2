"""Entity merge operations for canonical identity consolidation.

Provides propose/execute semantics:
  - ``propose_merge`` analyses two entities and returns a MergeResult
    with success=False (dry-run).
  - ``execute_merge`` commits the merge by setting merged_into_id and
    updating status.
  - ``resolve_merge_chain`` follows the merged_into chain to find the
    live canonical ancestor.

No LLM calls.  All merge decisions are rule-based (confidence threshold).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.graph.canonical_ids import normalize_entity_name
from app.graph.confidence import merge_confidence

_AUTO_MERGE_THRESHOLD = 0.90  # only auto-merge if confidence ≥ this


@dataclass
class MergeResult:
    """Result of a merge proposal or execution."""

    success: bool
    source_id: int  # entity being merged away
    target_id: int  # entity that survives
    confidence: float
    reason: str
    committed: bool = False  # True only after execute_merge


def propose_merge(
    db: Session,
    entity_a_id: int,
    entity_b_id: int,
) -> MergeResult:
    """Analyse whether two canonical entities should be merged.

    This is a **dry-run**: reads the DB but writes nothing.

    Confidence is derived from:
    - Normalised name similarity (exact = 0.95, fuzzy = 0.75)
    - Same entity_type (required)
    - Shared external ID (= 1.0)

    Args:
        db:           SQLAlchemy session.
        entity_a_id:  Primary key of entity A.
        entity_b_id:  Primary key of entity B.

    Returns:
        MergeResult with committed=False.
    """
    from app.models.entities import CanonicalEntity  # avoid circular at import

    entity_a = db.get(CanonicalEntity, entity_a_id)
    entity_b = db.get(CanonicalEntity, entity_b_id)

    if entity_a is None or entity_b is None:
        return MergeResult(
            success=False,
            source_id=entity_a_id,
            target_id=entity_b_id,
            confidence=0.0,
            reason="one or both entities not found",
        )

    if entity_a.entity_type != entity_b.entity_type:
        return MergeResult(
            success=False,
            source_id=entity_a_id,
            target_id=entity_b_id,
            confidence=0.0,
            reason=f"entity_type mismatch: {entity_a.entity_type!r} vs {entity_b.entity_type!r}",
        )

    # External ID match → highest confidence
    if (
        entity_a.canonical_id_external
        and entity_b.canonical_id_external
        and entity_a.canonical_id_external == entity_b.canonical_id_external
    ):
        return MergeResult(
            success=True,
            source_id=entity_a_id,
            target_id=entity_b_id,
            confidence=1.0,
            reason="external_id_match",
        )

    # Normalised name comparison
    norm_a = normalize_entity_name(entity_a.canonical_name)
    norm_b = normalize_entity_name(entity_b.canonical_name)

    if norm_a == norm_b:
        confidence = 0.95
        reason = "exact_name_match"
    else:
        import difflib

        ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
        if ratio >= 0.90:
            confidence = 0.80
            reason = f"fuzzy_name_match({ratio:.2f})"
        elif ratio >= 0.75:
            confidence = 0.65
            reason = f"weak_name_match({ratio:.2f})"
        else:
            return MergeResult(
                success=False,
                source_id=entity_a_id,
                target_id=entity_b_id,
                confidence=ratio,
                reason=f"name_too_dissimilar({ratio:.2f})",
            )

    return MergeResult(
        success=confidence >= _AUTO_MERGE_THRESHOLD,
        source_id=entity_a_id,
        target_id=entity_b_id,
        confidence=confidence,
        reason=reason,
    )


def execute_merge(
    db: Session,
    source_id: int,
    target_id: int,
    merged_by: str = "auto_resolver",
) -> MergeResult:
    """Commit a merge: mark source as merged_into target.

    Re-parents all EntitySourceRecord rows from source to target, then
    sets source.status = "merged_into" and source.merged_into_id = target.

    Args:
        db:        SQLAlchemy session (caller is responsible for commit).
        source_id: Entity to be retired.
        target_id: Entity that survives.
        merged_by: Audit identifier.

    Returns:
        MergeResult with committed=True on success.
    """
    from app.models.entities import (
        CanonicalEntity,
        EntitySourceRecord,
    )  # avoid circular

    source = db.get(CanonicalEntity, source_id)
    target = db.get(CanonicalEntity, target_id)

    if source is None or target is None:
        return MergeResult(
            success=False,
            source_id=source_id,
            target_id=target_id,
            confidence=0.0,
            reason="entity not found",
        )

    if source.status == "merged_into":
        return MergeResult(
            success=False,
            source_id=source_id,
            target_id=target_id,
            confidence=0.0,
            reason="source already merged",
        )

    # Re-parent source records
    (
        db.query(EntitySourceRecord)
        .filter(EntitySourceRecord.canonical_entity_id == source_id)
        .update({"canonical_entity_id": target_id}, synchronize_session="fetch")
    )

    # Mark source as absorbed
    source.status = "merged_into"
    source.merged_into_id = target_id
    source.notes = (
        f"Merged into {target_id} by {merged_by} at "
        f"{datetime.now(timezone.utc).isoformat()}"
    )

    # Update target confidence to reflect new merge confidence
    proposal = propose_merge(db, source_id, target_id)
    if proposal.confidence > 0:
        target.merge_confidence = merge_confidence(
            [target.merge_confidence, proposal.confidence]
        )

    return MergeResult(
        success=True,
        source_id=source_id,
        target_id=target_id,
        confidence=proposal.confidence,
        reason="executed",
        committed=True,
    )


def resolve_merge_chain(db: Session, entity_id: int) -> int:
    """Follow merged_into links to find the live canonical ancestor.

    Args:
        db:        SQLAlchemy session.
        entity_id: Starting entity primary key.

    Returns:
        Primary key of the entity that is still "active".
        Returns ``entity_id`` unchanged if it is already active.

    Raises:
        ValueError: If a cycle is detected (max 50 hops).
    """
    from app.models.entities import CanonicalEntity  # avoid circular

    seen: set[int] = set()
    current_id = entity_id

    while True:
        if current_id in seen:
            raise ValueError(f"merge cycle detected at entity {current_id}")
        seen.add(current_id)

        if len(seen) > 50:
            raise ValueError("merge chain exceeds 50 hops — possible cycle")

        entity = db.get(CanonicalEntity, current_id)
        if entity is None:
            return current_id  # best we can do

        if entity.status != "merged_into" or entity.merged_into_id is None:
            return current_id

        current_id = entity.merged_into_id


def propose_entity_merge(entity_a_id: int, entity_b_id: int, db: Session) -> dict:
    """Compatibility wrapper for legacy graph callers expecting dict output."""
    result = propose_merge(db, entity_a_id, entity_b_id)
    return {
        "success": result.success,
        "source_id": result.source_id,
        "target_id": result.target_id,
        "confidence": result.confidence,
        "reason": result.reason,
        "committed": result.committed,
    }
