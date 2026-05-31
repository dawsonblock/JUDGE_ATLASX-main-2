"""Deterministic trust-score propagation through EntityGraphEdge relationships.

Trust decays with each graph hop.  No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity, EntityGraphEdge

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRUST_DECAY: float = 0.85  # per hop — multiplier applied at each edge traversal
TIER_HIGH: str = "high"
TIER_MEDIUM: str = "medium"
TIER_LOW: str = "low"
TIER_UNTRUSTED: str = "untrusted"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustScore:
    """Computed trust score for a single canonical entity."""

    entity_id: int
    score: float  # 0.0–1.0
    contributing_sources: list[str]  # e.g. source_names gathered transitively
    decay_factor: float  # effective decay applied (product of per-hop factors)
    last_updated: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_trust_tier(score: float) -> str:
    """Map a 0–1 score to a named tier."""
    if score >= 0.80:
        return TIER_HIGH
    if score >= 0.55:
        return TIER_MEDIUM
    if score >= 0.30:
        return TIER_LOW
    return TIER_UNTRUSTED


def _base_trust(entity: Optional[CanonicalEntity]) -> float:
    """Return the base trust from the entity's stored score, or a default."""
    if entity is None:
        return 0.5
    stored = getattr(entity, "confidence_score", None) or getattr(
        entity, "merge_confidence", None
    )
    if stored is None:
        return 0.5
    return float(max(0.0, min(1.0, stored)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_trust(db: Session, entity_id: int) -> TrustScore:
    """Return the trust score for *entity_id* based on stored confidence + edge count."""
    entity: Optional[CanonicalEntity] = db.get(CanonicalEntity, entity_id)
    base = _base_trust(entity)

    # Collect edges where this entity is subject or object
    edges: list[EntityGraphEdge] = (
        db.query(EntityGraphEdge)
        .filter(
            EntityGraphEdge.status == "active",
            (EntityGraphEdge.subject_id == entity_id)
            | (EntityGraphEdge.object_id == entity_id),
        )
        .all()
    )

    # Boost slightly for corroborating edges (capped)
    edge_bonus = min(0.10, len(edges) * 0.01)
    score = min(1.0, base + edge_bonus)

    sources: list[str] = []
    if entity is not None and hasattr(entity, "source_records"):
        sources = [
            sr.source_name for sr in (entity.source_records or []) if sr.source_name
        ]

    return TrustScore(
        entity_id=entity_id,
        score=round(score, 4),
        contributing_sources=sources,
        decay_factor=1.0,
        last_updated=datetime.now(tz=timezone.utc),
    )


def propagate_trust(
    db: Session, source_entity_id: int, depth: int = 3
) -> list[TrustScore]:
    """BFS from *source_entity_id* up to *depth* hops; return TrustScore for each reached entity."""
    root_score = compute_trust(db, source_entity_id)
    result: dict[int, TrustScore] = {source_entity_id: root_score}

    frontier: list[tuple[int, float, float]] = [
        (source_entity_id, root_score.score, 1.0)
    ]
    visited: set[int] = {source_entity_id}

    for _hop in range(depth):
        next_frontier: list[tuple[int, float, float]] = []
        for current_id, current_score, current_decay in frontier:
            edges: list[EntityGraphEdge] = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.status == "active",
                    (EntityGraphEdge.subject_id == current_id)
                    | (EntityGraphEdge.object_id == current_id),
                )
                .all()
            )
            for edge in edges:
                neighbour_id = (
                    edge.object_id if edge.subject_id == current_id else edge.subject_id
                )
                if neighbour_id in visited:
                    continue
                visited.add(neighbour_id)

                new_decay = current_decay * TRUST_DECAY
                edge_weight = float(getattr(edge, "weight", 1.0) or 1.0)
                propagated = current_score * TRUST_DECAY * min(1.0, edge_weight)

                entity: Optional[CanonicalEntity] = db.get(
                    CanonicalEntity, neighbour_id
                )
                base = _base_trust(entity)
                blended = round((base + propagated) / 2.0, 4)

                sources: list[str] = []
                if entity is not None and hasattr(entity, "source_records"):
                    sources = [
                        sr.source_name
                        for sr in (entity.source_records or [])
                        if sr.source_name
                    ]

                ts = TrustScore(
                    entity_id=neighbour_id,
                    score=min(1.0, blended),
                    contributing_sources=sources,
                    decay_factor=new_decay,
                    last_updated=datetime.now(tz=timezone.utc),
                )
                result[neighbour_id] = ts
                next_frontier.append((neighbour_id, ts.score, new_decay))

        frontier = next_frontier
        if not frontier:
            break

    return list(result.values())
