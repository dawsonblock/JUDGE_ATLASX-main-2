"""Deterministic contradiction detection between MemoryClaim records.

Detects logical contradictions for claims of the same type on the same entity
using rule-based field comparison.  No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim
from app.services.text import normalize_text

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

RESOLUTION_A_WINS = "a_supersedes_b"
RESOLUTION_B_WINS = "b_supersedes_a"
RESOLUTION_UNRESOLVED = "unresolved"

CONTRADICTABLE_TYPES: frozenset[str] = frozenset(
    {
        "bail_amount",
        "release_decision",
        "case_outcome",
        "charge_status",
        "sentence_length",
        "current_status",
        "jurisdiction",
        "plea",
    }
)


@dataclass(frozen=True)
class ContradictionResult:
    """A detected contradiction between two MemoryClaim records."""

    claim_id_a: int
    claim_id_b: int
    entity_id: int
    claim_type: str
    value_a: str
    value_b: str
    confidence: float
    resolution: Optional[str] = None  # RESOLUTION_* constant or None


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------


def _score_contradiction(type_a: str, val_a: str, val_b: str) -> float:
    """Return a 0–1 confidence that the two values contradict each other."""
    if normalize_text(val_a) == normalize_text(val_b):
        return 0.0

    # Strongly contradictory value pairs per claim type
    _STRONG_PAIRS: dict[str, list[tuple[str, str]]] = {
        "release_decision": [("released", "detained"), ("bail_granted", "bail_denied")],
        "case_outcome": [("convicted", "acquitted"), ("guilty", "not_guilty")],
        "charge_status": [("charged", "dismissed"), ("active", "dropped")],
        "current_status": [("incarcerated", "released"), ("in_custody", "free")],
        "plea": [("guilty", "not_guilty"), ("no_contest", "not_guilty")],
    }

    pairs = _STRONG_PAIRS.get(type_a, [])
    norm_a = normalize_text(val_a)
    norm_b = normalize_text(val_b)
    for pa, pb in pairs:
        if (pa in norm_a and pb in norm_b) or (pb in norm_a and pa in norm_b):
            return 0.95

    # Numeric contradiction for numeric types
    if type_a in {"bail_amount", "sentence_length"}:
        try:
            fa = float("".join(c for c in val_a if c.isdigit() or c == "."))
            fb = float("".join(c for c in val_b if c.isdigit() or c == "."))
            if fa > 0 and fb > 0 and abs(fa - fb) / max(fa, fb) > 0.1:
                return 0.80
        except (ValueError, ZeroDivisionError):
            pass

    # Generic: non-equal values of a contradictable type
    if type_a in CONTRADICTABLE_TYPES and norm_a != norm_b:
        return 0.60

    return 0.0


def _resolve(claim_a: MemoryClaim, claim_b: MemoryClaim) -> Optional[str]:
    """Pick resolution by recency (newer claim wins)."""
    ts_a = claim_a.updated_at if hasattr(claim_a, "updated_at") else claim_a.created_at
    ts_b = claim_b.updated_at if hasattr(claim_b, "updated_at") else claim_b.created_at
    if ts_a is None and ts_b is None:
        return RESOLUTION_UNRESOLVED
    if ts_a is None:
        return RESOLUTION_B_WINS
    if ts_b is None:
        return RESOLUTION_A_WINS
    if ts_a > ts_b:
        return RESOLUTION_A_WINS
    if ts_b > ts_a:
        return RESOLUTION_B_WINS
    return RESOLUTION_UNRESOLVED


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_contradictions(db: Session, entity_id: int) -> list[ContradictionResult]:
    """Return all contradictions found among active claims for *entity_id*."""
    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )

    # Group by claim_type
    by_type: dict[str, list[MemoryClaim]] = {}
    for c in claims:
        if c.claim_type in CONTRADICTABLE_TYPES:
            by_type.setdefault(c.claim_type, []).append(c)

    results: list[ContradictionResult] = []
    for claim_type, group in by_type.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                ca, cb = group[i], group[j]
                score = _score_contradiction(claim_type, ca.claim_value, cb.claim_value)
                if score >= 0.50:
                    results.append(
                        ContradictionResult(
                            claim_id_a=ca.id,
                            claim_id_b=cb.id,
                            entity_id=entity_id,
                            claim_type=claim_type,
                            value_a=ca.claim_value,
                            value_b=cb.claim_value,
                            confidence=score,
                            resolution=_resolve(ca, cb),
                        )
                    )
    return results


def resolve_contradiction(
    db: Session, result: ContradictionResult, resolution: str
) -> None:
    """Apply *resolution* by deactivating the losing claim."""
    if resolution == RESOLUTION_A_WINS:
        losing_id = result.claim_id_b
    elif resolution == RESOLUTION_B_WINS:
        losing_id = result.claim_id_a
    else:
        return

    claim = db.get(MemoryClaim, losing_id)
    if claim is not None:
        claim.is_active = False
        claim.invalidation_reason = f"contradiction_resolved:{resolution}"
        db.flush()


def get_unresolved(db: Session) -> list[ContradictionResult]:
    """Return contradictions that have no automatic resolution (RESOLUTION_UNRESOLVED)."""
    all_entity_ids: list[int] = [
        row[0]
        for row in db.query(MemoryClaim.entity_id)
        .filter(MemoryClaim.is_active.is_(True))
        .distinct()
        .all()
    ]
    unresolved: list[ContradictionResult] = []
    for eid in all_entity_ids:
        for r in detect_contradictions(db, eid):
            if r.resolution == RESOLUTION_UNRESOLVED:
                unresolved.append(r)
    return unresolved
