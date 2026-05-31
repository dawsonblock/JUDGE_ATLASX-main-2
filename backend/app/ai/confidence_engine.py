"""Per-claim and per-entity confidence scoring using source quality and corroboration.

All logic is deterministic — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity, MemoryClaim

# ---------------------------------------------------------------------------
# Quality weights (0.0–1.0)
# ---------------------------------------------------------------------------

QUALITY_WEIGHTS: dict[str, float] = {
    "court_record": 1.00,
    "court_order": 0.98,
    "official_statement": 0.90,
    "official_police_open_data": 0.88,
    "official": 0.85,
    "academic": 0.75,
    "newspaper": 0.65,
    "news": 0.60,
    "blog": 0.40,
    "social": 0.30,
    "unknown": 0.20,
}

DEFAULT_QUALITY_WEIGHT: float = 0.40

# Corroboration bonus schedule: additional sources → extra points
_CORROBORATION_SCHEDULE: list[tuple[int, float]] = [
    (1, 0.00),
    (2, 0.05),
    (3, 0.08),
    (5, 0.10),
    (10, 0.12),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfidenceScore:
    """Computed confidence for a claim or entity."""

    subject_id: int
    subject_type: str  # "claim" | "entity"
    score: float  # 0.0–1.0
    source_count: int
    corroboration_bonus: float
    quality_weighted: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quality_weight(source_name: Optional[str]) -> float:
    if not source_name:
        return DEFAULT_QUALITY_WEIGHT
    for key, weight in QUALITY_WEIGHTS.items():
        if key in source_name.lower():
            return weight
    return DEFAULT_QUALITY_WEIGHT


def apply_corroboration_bonus(base: float, source_count: int) -> float:
    """Return the corroboration bonus for *source_count* distinct sources."""
    bonus = 0.0
    for threshold, value in reversed(_CORROBORATION_SCHEDULE):
        if source_count >= threshold:
            bonus = value
            break
    return bonus


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_claim(db: Session, claim_id: int) -> ConfidenceScore:
    """Compute confidence for a single claim."""
    claim: Optional[MemoryClaim] = db.get(MemoryClaim, claim_id)
    if claim is None:
        return ConfidenceScore(
            subject_id=claim_id,
            subject_type="claim",
            score=0.0,
            source_count=0,
            corroboration_bonus=0.0,
            quality_weighted=0.0,
        )

    stored = float(claim.confidence or 0.0)
    # Pull snapshot to determine source quality
    from app.models.entities import SourceSnapshot  # local import avoids cycles

    source_name: Optional[str] = None
    if claim.source_snapshot_id is not None:
        snap: Optional[SourceSnapshot] = db.get(
            SourceSnapshot, claim.source_snapshot_id
        )
        if snap is not None:
            source_name = getattr(snap, "source_key", None)

    qw = _quality_weight(source_name)
    # Blend stored confidence with quality weight
    quality_weighted = round((stored + qw) / 2.0, 4)
    bonus = apply_corroboration_bonus(quality_weighted, 1)
    final = round(min(1.0, quality_weighted + bonus), 4)

    return ConfidenceScore(
        subject_id=claim_id,
        subject_type="claim",
        score=final,
        source_count=1,
        corroboration_bonus=bonus,
        quality_weighted=quality_weighted,
    )


def score_entity(db: Session, entity_id: int) -> ConfidenceScore:
    """Compute aggregate confidence for an entity based on all its active claims."""
    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )

    if not claims:
        return ConfidenceScore(
            subject_id=entity_id,
            subject_type="entity",
            score=0.0,
            source_count=0,
            corroboration_bonus=0.0,
            quality_weighted=0.0,
        )

    source_count = len(claims)
    avg_claim_confidence = (
        sum(float(c.confidence or 0.0) for c in claims) / source_count
    )
    quality_weighted = round(avg_claim_confidence, 4)
    bonus = apply_corroboration_bonus(quality_weighted, source_count)
    final = round(min(1.0, quality_weighted + bonus), 4)

    return ConfidenceScore(
        subject_id=entity_id,
        subject_type="entity",
        score=final,
        source_count=source_count,
        corroboration_bonus=bonus,
        quality_weighted=quality_weighted,
    )
