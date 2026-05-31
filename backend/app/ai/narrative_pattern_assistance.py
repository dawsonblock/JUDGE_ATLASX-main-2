"""Narrative pattern detection across entity claims.

All rule-based — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim
from app.services.text import normalize_text

# ---------------------------------------------------------------------------
# Narrative pattern catalogue
# ---------------------------------------------------------------------------

NARRATIVE_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "repeat_offender",
        [
            "prior conviction",
            "repeat offender",
            "previous offense",
            "multiple arrests",
            "criminal history",
            "prior record",
            "habitual",
        ],
    ),
    (
        "escalation",
        [
            "escalating",
            "increased severity",
            "pattern of",
            "more serious",
            "step up",
            "graduated violence",
        ],
    ),
    (
        "exoneration",
        [
            "acquitted",
            "charges dropped",
            "wrongful conviction",
            "exonerated",
            "not guilty",
            "case dismissed",
            "conviction overturned",
            "conviction vacated",
            "innocence",
        ],
    ),
    (
        "systemic_bias",
        [
            "disproportionate",
            "racial disparity",
            "discriminatory",
            "over-policing",
            "disparate treatment",
            "profiling",
        ],
    ),
    (
        "cooperation",
        [
            "turned state witness",
            "cooperated with",
            "informant",
            "plea deal",
            "substantial assistance",
        ],
    ),
    (
        "flight_risk",
        [
            "flight risk",
            "failed to appear",
            "fta",
            "absconded",
            "evaded authorities",
            "fugitive",
        ],
    ),
]

_MIN_MATCH_CONFIDENCE: float = 0.30


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NarrativeMatch:
    entity_id: int
    pattern_name: str
    confidence: float
    matched_phrases: list[str]
    supporting_claims: list[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _match_text(text: str, phrases: list[str]) -> list[str]:
    """Return phrases found in *text* (after lowercasing)."""
    t = normalize_text(text)
    return [p for p in phrases if p in t]


def _build_narrative(
    entity_id: int,
    pattern_name: str,
    phrases: list[str],
    matched: list[str],
    claim_ids: list[int],
) -> Optional[NarrativeMatch]:
    if not matched:
        return None
    confidence = round(
        min(1.0, len(matched) / max(1, len(phrases)) + 0.20 * len(claim_ids)), 4
    )
    if confidence < _MIN_MATCH_CONFIDENCE:
        return None
    return NarrativeMatch(
        entity_id=entity_id,
        pattern_name=pattern_name,
        confidence=min(1.0, confidence),
        matched_phrases=matched,
        supporting_claims=claim_ids,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_from_text(text: str, entity_id: int = 0) -> list[NarrativeMatch]:
    """Detect narrative patterns in a single text string without DB access."""
    results: list[NarrativeMatch] = []
    for pattern_name, phrases in NARRATIVE_PATTERNS:
        matched = _match_text(text, phrases)
        nm = _build_narrative(entity_id, pattern_name, phrases, matched, claim_ids=[])
        if nm:
            results.append(nm)
    return results


def detect_narratives(db: Session, entity_id: int) -> list[NarrativeMatch]:
    """Detect narrative patterns across all active claims for *entity_id*."""
    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )

    if not claims:
        return []

    # Accumulate evidence per pattern
    pattern_state: dict[str, tuple[set[str], list[int]]] = {
        name: (set(), []) for name, _ in NARRATIVE_PATTERNS
    }

    for claim in claims:
        text = claim.claim_value or ""
        if claim.claim_value_json:
            if isinstance(claim.claim_value_json, dict):
                text += " " + " ".join(str(v) for v in claim.claim_value_json.values())
            elif isinstance(claim.claim_value_json, str):
                text += " " + claim.claim_value_json

        for pattern_name, phrases in NARRATIVE_PATTERNS:
            matched = _match_text(text, phrases)
            if matched:
                accumulated_phrases, accumulated_claims = pattern_state[pattern_name]
                accumulated_phrases.update(matched)
                accumulated_claims.append(claim.id)

    results: list[NarrativeMatch] = []
    for pattern_name, phrases in NARRATIVE_PATTERNS:
        accumulated_phrases, accumulated_claims = pattern_state[pattern_name]
        nm = _build_narrative(
            entity_id,
            pattern_name,
            phrases,
            list(accumulated_phrases),
            accumulated_claims,
        )
        if nm:
            results.append(nm)

    return results
