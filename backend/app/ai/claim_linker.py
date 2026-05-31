"""Rule-based linker that associates MemoryClaim records with CanonicalEntity rows.

Matching uses claim_value text similarity against canonical_name.  No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity, MemoryClaim
from app.services.text import normalize_text

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

LINK_TYPE_EXACT = "exact_name"
LINK_TYPE_PARTIAL = "partial_name"
LINK_TYPE_CLAIM_SELF = "claim_self_ref"


@dataclass(frozen=True)
class ClaimLink:
    """A detected link between a MemoryClaim and a CanonicalEntity."""

    claim_id: int
    entity_id: int
    link_type: str
    confidence: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    """Compute token Jaccard similarity between two normalised strings."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


def _try_link(
    claim: MemoryClaim, candidates: list[CanonicalEntity]
) -> Optional[ClaimLink]:
    """Return the best ClaimLink for this claim, or None if below threshold."""
    norm_val = normalize_text(claim.claim_value)
    best_score = 0.0
    best_entity: Optional[CanonicalEntity] = None
    best_link_type = LINK_TYPE_PARTIAL

    for entity in candidates:
        norm_name = normalize_text(entity.canonical_name)
        if norm_val == norm_name:
            return ClaimLink(
                claim_id=claim.id,
                entity_id=entity.id,
                link_type=LINK_TYPE_EXACT,
                confidence=1.0,
            )
        sim = _similarity(norm_val, norm_name)
        if sim > best_score:
            best_score = sim
            best_entity = entity

    if best_entity is not None and best_score >= 0.60:
        return ClaimLink(
            claim_id=claim.id,
            entity_id=best_entity.id,
            link_type=LINK_TYPE_PARTIAL,
            confidence=round(best_score, 4),
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def link_claim_to_entity(db: Session, claim_id: int) -> Optional[ClaimLink]:
    """Find a CanonicalEntity match for the given claim.

    Returns a ClaimLink if confidence ≥ 0.60, otherwise None.
    """
    claim: Optional[MemoryClaim] = db.get(MemoryClaim, claim_id)
    if claim is None:
        return None

    # If the claim already references an entity, return a self-ref link
    if claim.entity_id:
        return ClaimLink(
            claim_id=claim.id,
            entity_id=claim.entity_id,
            link_type=LINK_TYPE_CLAIM_SELF,
            confidence=1.0,
        )

    candidates: list[CanonicalEntity] = (
        db.query(CanonicalEntity).filter(CanonicalEntity.status == "active").all()
    )
    return _try_link(claim, candidates)


def bulk_link_unlinked(db: Session, limit: int = 100) -> list[ClaimLink]:
    """Attempt to link up to *limit* claims that have no entity reference."""
    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(MemoryClaim.entity_id.is_(None), MemoryClaim.is_active.is_(True))
        .limit(limit)
        .all()
    )
    candidates: list[CanonicalEntity] = (
        db.query(CanonicalEntity).filter(CanonicalEntity.status == "active").all()
    )
    links: list[ClaimLink] = []
    for claim in claims:
        link = _try_link(claim, candidates)
        if link is not None:
            links.append(link)
    return links


def get_entity_claims(db: Session, entity_id: int) -> list[MemoryClaim]:
    """Return all active claims for *entity_id*."""
    return (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )
