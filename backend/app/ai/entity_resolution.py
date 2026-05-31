"""Rule-based entity deduplication using name normalization and attribute similarity.

Complements the lower-level canonical_resolver.  No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity
from app.services.text import normalize_name, normalize_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MERGE = "merge"
DISTINCT = "distinct"
UNCERTAIN = "uncertain"

DEFAULT_THRESHOLD: float = 0.80


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionCandidate:
    """A pair of entities that may be duplicates."""

    entity_id_a: int
    entity_id_b: int
    similarity: float
    matching_fields: list[str]
    resolution: str  # MERGE | DISTINCT | UNCERTAIN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_sim(a: str, b: str) -> float:
    """Token Jaccard similarity between two strings."""
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _field_score(
    entity_a: CanonicalEntity, entity_b: CanonicalEntity
) -> tuple[float, list[str]]:
    """Return (similarity, matching_fields) based on rule comparison."""
    matches: list[str] = []
    scores: list[float] = []

    # --- canonical_name ---
    na = normalize_name(entity_a.canonical_name)
    nb = normalize_name(entity_b.canonical_name)
    name_sim = _token_sim(na, nb)
    scores.append(name_sim)
    if name_sim >= 0.90:
        matches.append("canonical_name")

    # --- external ID ---
    id_a = getattr(entity_a, "canonical_id_external", None)
    id_b = getattr(entity_b, "canonical_id_external", None)
    if id_a and id_b and str(id_a).strip() == str(id_b).strip():
        matches.append("canonical_id_external")
        scores.append(1.0)

    # --- entity_type must match ---
    if entity_a.entity_type != entity_b.entity_type:
        return 0.0, []

    avg = sum(scores) / len(scores) if scores else 0.0
    return round(avg, 4), matches


def _classify(sim: float, threshold: float) -> str:
    if sim >= threshold:
        return MERGE
    if sim <= 0.30:
        return DISTINCT
    return UNCERTAIN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_candidates(
    db: Session, entity_id: int, threshold: float = DEFAULT_THRESHOLD
) -> list[ResolutionCandidate]:
    """Find entities similar to *entity_id* above *threshold*."""
    target: Optional[CanonicalEntity] = db.get(CanonicalEntity, entity_id)
    if target is None:
        return []

    peers: list[CanonicalEntity] = (
        db.query(CanonicalEntity)
        .filter(
            CanonicalEntity.id != entity_id,
            CanonicalEntity.entity_type == target.entity_type,
            CanonicalEntity.status == "active",
        )
        .all()
    )

    candidates: list[ResolutionCandidate] = []
    for peer in peers:
        sim, matching = _field_score(target, peer)
        if sim >= threshold * 0.75:  # surface uncertain as well
            candidates.append(
                ResolutionCandidate(
                    entity_id_a=entity_id,
                    entity_id_b=peer.id,
                    similarity=sim,
                    matching_fields=matching,
                    resolution=_classify(sim, threshold),
                )
            )
    return candidates


def resolve_candidate(db: Session, candidate: ResolutionCandidate) -> bool:
    """Apply a MERGE resolution by marking entity_b as merged into entity_a.

    Returns True if action was taken.
    """
    if candidate.resolution != MERGE:
        return False

    entity_b: Optional[CanonicalEntity] = db.get(CanonicalEntity, candidate.entity_id_b)
    if entity_b is None:
        return False

    entity_b.status = "merged_into"
    entity_b.merged_into_id = candidate.entity_id_a
    db.flush()
    return True


def bulk_resolve(db: Session, limit: int = 50) -> list[ResolutionCandidate]:
    """Find and return up to *limit* MERGE candidates across all active entities."""
    entities: list[CanonicalEntity] = (
        db.query(CanonicalEntity)
        .filter(CanonicalEntity.status == "active")
        .limit(limit * 2)
        .all()
    )

    seen: set[tuple[int, int]] = set()
    results: list[ResolutionCandidate] = []

    for entity in entities:
        if len(results) >= limit:
            break
        for candidate in find_candidates(db, entity.id, threshold=DEFAULT_THRESHOLD):
            key = (
                min(candidate.entity_id_a, candidate.entity_id_b),
                max(candidate.entity_id_a, candidate.entity_id_b),
            )
            if key not in seen and candidate.resolution == MERGE:
                seen.add(key)
                results.append(candidate)

    return results
