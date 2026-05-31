"""Contradiction engine for detecting conflicting claims.

Implements logic to detect contradictions between claims about the same entity.
Persist contradictions to database for durable tracking and review.
"""

import logging
from collections import defaultdict
from typing import List, Dict, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.models.entities import (
    MemoryClaim,
    CanonicalEntity,
    MemoryContradiction,
    LegalSource,
)
from app.memory.source_authority import get_source_authority_weight

logger = logging.getLogger(__name__)


def _get_source_authority_weight(source: LegalSource | str | None) -> float:
    """Compatibility wrapper for legacy tests/callers.

    Accepts either a LegalSource instance, source_type string, or None.
    """
    if isinstance(source, LegalSource):
        return get_source_authority_weight(source.source_type)
    return get_source_authority_weight(source)


def detect_contradictions(
    entity_id: int | List[MemoryClaim], db: Session, persist: bool = True
) -> List[Dict[str, any]]:
    """Detect contradictions between claims for a given entity.

    Args:
        entity_id: Entity ID to check, or a pre-fetched list of claims
        db: Database session
        persist: Whether to persist contradictions to database

    Returns:
        List of contradiction dictionaries with details
    """
    if isinstance(entity_id, list):
        claims = entity_id
    else:
        # Get all active claims for the entity
        # Only include claims with status "active" to exclude superseded, disputed, rejected claims
        claims = (
            db.query(MemoryClaim)
            .filter(
                MemoryClaim.entity_id == entity_id,
                MemoryClaim.is_active,
                MemoryClaim.status == "active",
            )
            .all()
        )

    # Pre-fetch source snapshots and legal sources to avoid N+1 queries
    from app.models.entities import SourceSnapshot
    source_snapshot_ids = [c.source_snapshot_id for c in claims if c.source_snapshot_id]
    snapshots_map = {}
    if source_snapshot_ids:
        snapshots = db.query(SourceSnapshot).filter(
            SourceSnapshot.id.in_(source_snapshot_ids)
        ).all()
        snapshots_map = {s.id: s for s in snapshots}

    # Pre-fetch legal sources for all snapshots (legacy source_id and current source_key)
    legal_source_ids = [
        s.source_id
        for s in snapshots_map.values()
        if getattr(s, "source_id", None) is not None
    ]
    legal_source_keys = [
        str(s.source_key)
        for s in snapshots_map.values()
        if getattr(s, "source_key", None)
    ]
    sources_map = {}
    sources_by_key = {}
    if legal_source_ids:
        sources = db.query(LegalSource).filter(
            LegalSource.id.in_(legal_source_ids)
        ).all()
        sources_map = {s.id: s for s in sources}
    if legal_source_keys:
        key_sources = db.query(LegalSource).filter(
            LegalSource.source_id.in_(legal_source_keys)
        ).all()
        sources_by_key = {s.source_id: s for s in key_sources}

    # Build a cache mapping claim_id -> source authority weight
    source_authority_cache = {}
    for claim in claims:
        if claim.source_snapshot_id and claim.source_snapshot_id in snapshots_map:
            snapshot = snapshots_map[claim.source_snapshot_id]
            source = None
            snapshot_source_id = getattr(snapshot, "source_id", None)
            snapshot_source_key = getattr(snapshot, "source_key", None)
            if snapshot_source_id in sources_map:
                source = sources_map[snapshot_source_id]
            elif snapshot_source_key:
                source = sources_by_key.get(str(snapshot_source_key))
            if source is not None:
                source_authority_cache[claim.id] = get_source_authority_weight(
                    source.source_type
                )

    contradictions = []
    # Group claims by predicate
    claims_by_predicate: Dict[str, List[MemoryClaim]] = {}
    for claim in claims:
        predicate = claim.predicate or "unknown"
        if predicate not in claims_by_predicate:
            claims_by_predicate[predicate] = []
        claims_by_predicate[predicate].append(claim)

    for predicate, predicate_claims in claims_by_predicate.items():
        if len(predicate_claims) < 2:
            continue

        # Map predicates to their specific check functions
        predicate_checks = {
            "case_status": _check_case_status_conflict,
            "sentence": _check_sentence_conflict,
            "appeal_outcome": _check_appeal_outcome_conflict,
            "statute_section": _check_statute_version_conflict,
            "court_level": _check_court_level_conflict,
            "assigned_judge": _check_judge_assignment_conflict,
            "legal_name": _check_identity_conflict,
            "same_as": _check_identity_conflict,
        }
        check_func = predicate_checks.get(predicate)

        # For each unique claim pair
        for i, claim1 in enumerate(predicate_claims):
            for claim2 in predicate_claims[i + 1 :]:
                # Priority for generic checks: temporal > value.
                # Predicate-specific contradictions are checked separately and may
                # provide more precise legal conflict typing than generic value diff.
                temporal = _check_temporal_contradiction(claim1, claim2, db, source_authority_cache)
                if temporal:
                    contradictions.append(temporal)
                    if persist:
                        _persist_contradiction(temporal, db)
                if check_func:
                    contradiction = check_func(claim1, claim2, db, source_authority_cache)
                    if contradiction:
                        contradictions.append(contradiction)
                        if persist:
                            _persist_contradiction(contradiction, db)
                        # Prefer specific legal contradiction type to generic value.
                        continue

                if temporal:
                    # Do not also emit generic value contradiction for same pair.
                    continue

                value = _check_value_contradiction(claim1, claim2, db, source_authority_cache)
                if value:
                    contradictions.append(value)
                    if persist:
                        _persist_contradiction(value, db)

    return contradictions


def _persist_contradiction(
    contradiction: Dict[str, any], db: Session
) -> Optional[MemoryContradiction]:
    """Persist a contradiction to the database.

    Args:
        contradiction: Contradiction dictionary
        db: Database session

    Returns:
        Persisted MemoryContradiction or None if already exists
    """
    from app.models.entities import SourceSnapshot

    claim1_id = contradiction["claim1_id"]
    claim2_id = contradiction["claim2_id"]
    conflict_type = contradiction.get("type")

    # Check if contradiction already exists (check both directions to prevent duplicates)
    existing = (
        db.query(MemoryContradiction)
        .filter(
            ((MemoryContradiction.claim_a_id == claim1_id) & (MemoryContradiction.claim_b_id == claim2_id)) |
            ((MemoryContradiction.claim_a_id == claim2_id) & (MemoryContradiction.claim_b_id == claim1_id))
        )
        .first()
    )
    if existing:
        return existing

    # Calculate source authority weight for the contradiction
    claim1 = db.query(MemoryClaim).filter(MemoryClaim.id == claim1_id).first()
    claim2 = db.query(MemoryClaim).filter(MemoryClaim.id == claim2_id).first()

    source1 = None
    source2 = None
    if claim1 and claim1.source_snapshot_id:
        snapshot1 = db.query(SourceSnapshot).filter(
            SourceSnapshot.id == claim1.source_snapshot_id
        ).first()
        if snapshot1:
            snapshot_source_id = getattr(snapshot1, "source_id", None)
            snapshot_source_key = getattr(snapshot1, "source_key", None)
            if snapshot_source_id is not None:
                source1 = db.query(LegalSource).filter(
                    LegalSource.id == snapshot_source_id
                ).first()
            elif snapshot_source_key:
                source1 = db.query(LegalSource).filter(
                    LegalSource.source_id == str(snapshot_source_key)
                ).first()
    if claim2 and claim2.source_snapshot_id:
        snapshot2 = db.query(SourceSnapshot).filter(
            SourceSnapshot.id == claim2.source_snapshot_id
        ).first()
        if snapshot2:
            snapshot_source_id = getattr(snapshot2, "source_id", None)
            snapshot_source_key = getattr(snapshot2, "source_key", None)
            if snapshot_source_id is not None:
                source2 = db.query(LegalSource).filter(
                    LegalSource.id == snapshot_source_id
                ).first()
            elif snapshot_source_key:
                source2 = db.query(LegalSource).filter(
                    LegalSource.source_id == str(snapshot_source_key)
                ).first()

    weight1 = get_source_authority_weight(source1.source_type if source1 else None)
    weight2 = get_source_authority_weight(source2.source_type if source2 else None)
    # Use the higher authority weight for the contradiction
    authority_weight = max(weight1, weight2)

    # Create new contradiction record
    new_contradiction = MemoryContradiction(
        claim_a_id=claim1_id,
        claim_b_id=claim2_id,
        conflict_type=conflict_type,
        severity=contradiction.get("severity", "medium"),
        status="open",
        detected_by="system",
        detected_at=datetime.now(timezone.utc),
        source_authority_weight=authority_weight,
    )
    db.add(new_contradiction)

    try:
        # Increment contradiction counts on both claims
        if claim1:
            claim1.contradiction_count += 1
        else:
            logger.warning(
                "Claim %d not found when persisting contradiction",
                claim1_id
            )
        if claim2:
            claim2.contradiction_count += 1
        else:
            logger.warning(
                "Claim %d not found when persisting contradiction",
                claim2_id
            )

        db.commit()
        logger.info(
            "Persisted contradiction between claims %d and %d (type: %s, authority_weight: %.2f)",
            claim1_id,
            claim2_id,
            conflict_type,
            authority_weight,
        )

        return new_contradiction
    except IntegrityError:
        # Handle race condition where another process inserted the same contradiction
        db.rollback()
        # Query again to get the existing record
        existing = (
            db.query(MemoryContradiction)
            .filter(
                (
                    (MemoryContradiction.claim_a_id == claim1_id)
                    & (MemoryContradiction.claim_b_id == claim2_id)
                )
                | (
                    (MemoryContradiction.claim_a_id == claim2_id)
                    & (MemoryContradiction.claim_b_id == claim1_id)
                ),
                MemoryContradiction.conflict_type == conflict_type,
            )
            .first()
        )
        if existing:
            logger.info(
                "Contradiction already exists between claims %d and %d (type: %s)",
                claim1_id,
                claim2_id,
                conflict_type,
            )
            return existing
        logger.error(
            "Failed to find contradiction after IntegrityError rollback "
            f"for claims {claim1_id} and {claim2_id} (type: {conflict_type})",
        )
        return None


def _calculate_severity(
    contradiction_type: str,
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> str:
    """Calculate contradiction severity based on multiple factors.

    Args:
        contradiction_type: Type of contradiction
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Severity level: "critical", "high", "medium", "low"
    """
    # Use cached source authority weights if available
    if source_authority_cache:
        weight1 = source_authority_cache.get(claim1.id, 1.0)
        weight2 = source_authority_cache.get(claim2.id, 1.0)
    else:
        # Fallback to database queries for backward compatibility
        weight1 = 1.0  # default unknown (neutral)
        if claim1.source_snapshot_id:
            from app.models.entities import SourceSnapshot
            snapshot1 = db.query(SourceSnapshot).filter(
                SourceSnapshot.id == claim1.source_snapshot_id
            ).first()
            if snapshot1:
                source1 = db.query(LegalSource).filter(
                    LegalSource.id == snapshot1.source_id
                ).first()
                if source1:
                    weight1 = get_source_authority_weight(source1.source_type)

        weight2 = 1.0  # default unknown (neutral)
        if claim2.source_snapshot_id:
            from app.models.entities import SourceSnapshot
            snapshot2 = db.query(SourceSnapshot).filter(
                SourceSnapshot.id == claim2.source_snapshot_id
            ).first()
            if snapshot2:
                source2 = db.query(LegalSource).filter(
                    LegalSource.id == snapshot2.source_id
                ).first()
                if source2:
                    weight2 = get_source_authority_weight(source2.source_type)

    max_authority = max(weight1, weight2)

    # Base severity from contradiction type
    base_severity = {
        "value_contradiction": 0.5,
        "temporal_contradiction": 0.3,
    }.get(contradiction_type, 0.4)

    # Adjust by source authority (higher authority = higher severity)
    authority_factor = max_authority  # 0.0-1.0

    # Adjust by claim confidence (higher confidence = higher severity)
    confidence_factor = max(claim1.confidence or 0.5, claim2.confidence or 0.5)

    # Adjust by entity importance (critical entities = higher severity)
    entity_importance_factor = 1.0
    if claim1.entity_id:
        entity = db.query(CanonicalEntity).filter(CanonicalEntity.id == claim1.entity_id).first()
        if entity and entity.entity_type in ["person", "organization"]:
            entity_importance_factor = 1.2

    # Calculate final severity (0.0-1.0)
    final_severity = base_severity * authority_factor * confidence_factor * entity_importance_factor
    final_severity = min(final_severity, 1.0)  # Cap at 1.0

    # Map to severity levels
    if final_severity >= 0.8:
        return "critical"
    elif final_severity >= 0.5:
        return "high"
    elif final_severity >= 0.3:
        return "medium"
    else:
        return "low"


def _check_value_contradiction(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check if two claims have contradictory values.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    # Skip if values are the same
    if claim1.normalized_value == claim2.normalized_value:
        return None

    # Skip if either claim lacks normalized value
    if not claim1.normalized_value or not claim2.normalized_value:
        return None

    # Check for explicit contradictions based on value type
    if claim1.object_value_type == "boolean" and claim2.object_value_type == "boolean":
        val1 = claim1.normalized_value.lower()
        val2 = claim2.normalized_value.lower()
        if (val1 == "true" and val2 == "false") or (val1 == "false" and val2 == "true"):
            # Explicit boolean inversions are high-impact contradictions even when
            # source-authority metadata is unavailable.
            severity = "high"
            return {
                "type": "value_contradiction",
                "claim1_id": claim1.id,
                "claim2_id": claim2.id,
                "predicate": claim1.predicate,
                "value1": claim1.normalized_value,
                "value2": claim2.normalized_value,
                "severity": severity,
            }

    # Check for numeric contradictions (significant difference)
    if claim1.object_value_type == "number" and claim2.object_value_type == "number":
        try:
            num1 = float(claim1.normalized_value)
            num2 = float(claim2.normalized_value)
            # If values differ by more than 10%, consider it a contradiction
            if num1 > 0 and abs(num1 - num2) / num1 > 0.1:
                severity = _calculate_severity(
                "value_contradiction", claim1, claim2, db, source_authority_cache
            )
                return {
                    "type": "value_contradiction",
                    "claim1_id": claim1.id,
                    "claim2_id": claim2.id,
                    "predicate": claim1.predicate,
                    "value1": claim1.normalized_value,
                    "value2": claim2.normalized_value,
                    "severity": severity,
                }
        except (ValueError, TypeError):
            pass

    # Generic textual contradiction fallback for same-predicate claims.
    if claim1.predicate and claim1.predicate == claim2.predicate:
        text_like_types = {None, "text", "string", "literal", "entity"}
        if claim1.object_value_type in text_like_types and claim2.object_value_type in text_like_types:
            severity = _calculate_severity(
                "value_contradiction", claim1, claim2, db, source_authority_cache
            )
            return {
                "type": "value_contradiction",
                "claim1_id": claim1.id,
                "claim2_id": claim2.id,
                "predicate": claim1.predicate,
                "value1": claim1.normalized_value,
                "value2": claim2.normalized_value,
                "severity": severity,
            }

    return None


def _check_temporal_contradiction(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check if two claims have contradictory temporal validity.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    # Skip if either claim lacks valid_from — no temporal window to compare.
    if not claim1.valid_from or not claim2.valid_from:
        return None

    # Skip if values are the same — overlapping windows with identical values aren't contradictions.
    if claim1.normalized_value == claim2.normalized_value:
        return None

    # Determine window endpoints; use far-future sentinel for open-ended windows.
    FAR_FUTURE = datetime(9999, 12, 31, tzinfo=timezone.utc)

    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    start1 = _as_utc(claim1.valid_from)
    start2 = _as_utc(claim2.valid_from)
    end1 = _as_utc(claim1.valid_to) if claim1.valid_to else FAR_FUTURE
    end2 = _as_utc(claim2.valid_to) if claim2.valid_to else FAR_FUTURE

    # Windows overlap when max(start) < min(end).
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)

    if overlap_start >= overlap_end:
        return None  # Non-overlapping windows — not a temporal contradiction.

    severity = _calculate_severity(
        "temporal_contradiction", claim1, claim2, db, source_authority_cache
    )
    return {
        "type": "temporal_contradiction",
        "claim1_id": claim1.id,
        "claim2_id": claim2.id,
        "predicate": claim1.predicate,
        "valid_from": str(claim1.valid_from),
        "value1": claim1.normalized_value,
        "value2": claim2.normalized_value,
        "severity": severity,
    }


def _check_case_status_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for case status contradictions.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "case_status" or claim2.predicate != "case_status":
        return None

    # Mutually exclusive case statuses
    contradictory_statuses = {
        ("convicted", "acquitted"),
        ("convicted", "dismissed"),
        ("convicted", "not_guilty"),
        ("acquitted", "convicted"),
        ("dismissed", "convicted"),
        ("not_guilty", "convicted"),
    }

    val1 = claim1.normalized_value.lower() if claim1.normalized_value else ""
    val2 = claim2.normalized_value.lower() if claim2.normalized_value else ""

    if (val1, val2) in contradictory_statuses:
        severity = _calculate_severity(
            "case_status_conflict", claim1, claim2, db, source_authority_cache
        )
        return {
            "type": "case_status_conflict",
            "claim1_id": claim1.id,
            "claim2_id": claim2.id,
            "predicate": "case_status",
            "value1": claim1.normalized_value,
            "value2": claim2.normalized_value,
            "severity": severity,
        }

    return None


def _check_sentence_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for sentence contradictions (sentenced vs not sentenced).

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "sentence" or claim2.predicate != "sentence":
        return None

    val1 = claim1.normalized_value.lower() if claim1.normalized_value else ""
    val2 = claim2.normalized_value.lower() if claim2.normalized_value else ""

    # Any materially different sentence values are contradictory.
    if val1 and val2 and val1 != val2:
        severity = _calculate_severity(
            "sentence_conflict", claim1, claim2, db, source_authority_cache
        )
        return {
            "type": "sentence_conflict",
            "claim1_id": claim1.id,
            "claim2_id": claim2.id,
            "predicate": "sentence",
            "value1": claim1.normalized_value,
            "value2": claim2.normalized_value,
            "severity": severity,
        }

    return None


def _check_appeal_outcome_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for appeal outcome contradictions.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "appeal_outcome" or claim2.predicate != "appeal_outcome":
        return None

    val1 = claim1.normalized_value.lower() if claim1.normalized_value else ""
    val2 = claim2.normalized_value.lower() if claim2.normalized_value else ""

    contradictory_outcomes = {
        ("upheld", "overturned"),
        ("upheld", "reversed"),
        ("overturned", "upheld"),
        ("reversed", "upheld"),
        ("affirmed", "reversed"),
        ("reversed", "affirmed"),
    }

    if (val1, val2) in contradictory_outcomes:
        severity = _calculate_severity(
            "appeal_outcome_conflict", claim1, claim2, db, source_authority_cache
        )
        return {
            "type": "appeal_outcome_conflict",
            "claim1_id": claim1.id,
            "claim2_id": claim2.id,
            "predicate": "appeal_outcome",
            "value1": claim1.normalized_value,
            "value2": claim2.normalized_value,
            "severity": severity,
        }

    return None


def _check_statute_version_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for statute version conflicts.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "statute_section" or claim2.predicate != "statute_section":
        return None

    # Check if same statute has different section numbers
    if claim1.normalized_value != claim2.normalized_value:
        # Extract statute ID (before the section number) to check if they're from the same statute
        # Example: "C-46 s.123(1)" -> statute ID is "C-46"
        val1 = claim1.normalized_value or ""
        val2 = claim2.normalized_value or ""

        # Try to extract statute ID (pattern: letters/numbers before space or section marker)
        import re
        statute_id_pattern = r'^[A-Za-z0-9\-]+'
        statute1 = re.match(statute_id_pattern, val1)
        statute2 = re.match(statute_id_pattern, val2)

        # Only flag as contradiction if they're from the same statute
        # Different sections of the same statute are not contradictions
        if statute1 and statute2 and statute1.group() == statute2.group():
            severity = _calculate_severity(
                "statute_version_conflict", claim1, claim2, db, source_authority_cache
            )
            return {
                "type": "statute_version_conflict",
                "claim1_id": claim1.id,
                "claim2_id": claim2.id,
                "predicate": "statute_section",
                "value1": claim1.normalized_value,
                "value2": claim2.normalized_value,
                "severity": severity,
            }

    return None


def _check_court_level_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for court level contradictions.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "court_level" or claim2.predicate != "court_level":
        return None

    val1 = claim1.normalized_value.lower() if claim1.normalized_value else ""
    val2 = claim2.normalized_value.lower() if claim2.normalized_value else ""

    # Check for contradictory court levels
    contradictory_levels = {
        ("provincial", "federal"),
        ("federal", "provincial"),
        ("superior_court", "provincial_court"),
        ("provincial_court", "superior_court"),
        ("court_of_appeal", "provincial_court"),
        ("provincial_court", "court_of_appeal"),
        ("trial_court", "appellate_court"),
        ("appellate_court", "trial_court"),
    }

    if (val1, val2) in contradictory_levels:
        severity = _calculate_severity(
            "court_level_conflict", claim1, claim2, db, source_authority_cache
        )
        return {
            "type": "court_level_conflict",
            "claim1_id": claim1.id,
            "claim2_id": claim2.id,
            "predicate": "court_level",
            "value1": claim1.normalized_value,
            "value2": claim2.normalized_value,
            "severity": severity,
        }

    return None


def _check_judge_assignment_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for judge assignment contradictions.

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != "assigned_judge" or claim2.predicate != "assigned_judge":
        return None

    if claim1.normalized_value and claim2.normalized_value:
        if claim1.normalized_value != claim2.normalized_value:
            severity = _calculate_severity(
                "judge_assignment_conflict", claim1, claim2, db, source_authority_cache
            )
            return {
                "type": "judge_assignment_conflict",
                "claim1_id": claim1.id,
                "claim2_id": claim2.id,
                "predicate": "assigned_judge",
                "value1": claim1.normalized_value,
                "value2": claim2.normalized_value,
                "hearing_date": str(claim1.observed_at.date()) if claim1.observed_at else None,
                "severity": severity,
            }

    return None


def _check_identity_conflict(
    claim1: MemoryClaim,
    claim2: MemoryClaim,
    db: Session,
    source_authority_cache: Optional[Dict[int, float]] = None,
) -> Optional[Dict[str, any]]:
    """Check for identity contradictions (same entity, different values).

    Args:
        claim1: First claim
        claim2: Second claim
        db: Database session
        source_authority_cache: Optional cache mapping claim_id -> source authority weight

    Returns:
        Contradiction dict if found, None otherwise
    """
    if claim1.predicate != claim2.predicate:
        return None
    if claim1.predicate not in {"legal_name", "same_as"}:
        return None

    # Check if same entity has conflicting identity values.
    if claim1.entity_id == claim2.entity_id:
        if claim1.normalized_value != claim2.normalized_value:
            severity = _calculate_severity(
                "identity_conflict", claim1, claim2, db, source_authority_cache
            )
            return {
                "type": "identity_conflict",
                "claim1_id": claim1.id,
                "claim2_id": claim2.id,
                "predicate": claim1.predicate,
                "value1": claim1.normalized_value,
                "value2": claim2.normalized_value,
                "severity": severity,
            }

    return None


def update_contradiction_counts(db: Session) -> int:
    """Update contradiction counts for all entities.

    Args:
        db: Database session

    Returns:
        Number of entities with contradictions
    """
    BATCH_SIZE = 1000
    offset = 0
    entities_with_contradictions = 0

    while True:
        entities = (
            db.query(CanonicalEntity)
            .offset(offset)
            .limit(BATCH_SIZE)
            .all()
        )

        if not entities:
            break

        for entity in entities:
            contradictions = detect_contradictions(entity.id, db)
            contradiction_count = len(contradictions)

            # Update contradiction counts for all claims on this entity
            claims = (
                db.query(MemoryClaim)
                .filter(MemoryClaim.entity_id == entity.id)
                .all()
            )
            for claim in claims:
                claim.contradiction_count = contradiction_count

            if contradiction_count > 0:
                entities_with_contradictions += 1

        db.commit()
        offset += BATCH_SIZE

    logger.info(
        "Updated contradiction counts for %d entities",
        entities_with_contradictions,
    )

    return entities_with_contradictions


def resolve_contradiction(
    claim_id: int, resolution: str, db: Session
) -> bool:
    """Resolve a contradiction by marking the claim as superseded.

    Args:
        claim_id: ID of the claim to resolve
        resolution: Resolution type (supersede, invalidate, retain)
        db: Database session

    Returns:
        True if resolution succeeded, False otherwise
    """
    claim = db.query(MemoryClaim).filter(MemoryClaim.id == claim_id).first()
    if not claim:
        logger.warning("Claim %d not found for contradiction resolution", claim_id)
        return False

    if resolution == "supersede":
        claim.status = "superseded"
        claim.is_active = False
        claim.invalidation_reason = "Contradiction resolved by supersession"
        claim.invalidated_at = claim.updated_at
    elif resolution == "invalidate":
        claim.status = "invalid"
        claim.is_active = False
        claim.invalidation_reason = "Contradiction resolved by invalidation"
        claim.invalidated_at = claim.updated_at
    elif resolution == "retain":
        # Keep the claim active, update contradiction count
        pass
    else:
        logger.warning("Invalid resolution type: %s", resolution)
        return False

    db.commit()
    logger.info(
        "Resolved contradiction for claim %d with resolution: %s",
        claim_id,
        resolution,
    )

    # Update contradiction counts for the entity
    update_contradiction_counts(db)

    return True


def auto_supersede_by_authority(contradiction_id: int, db: Session) -> bool:
    """Automatically supersede lower-authority claim in a contradiction.

    If one claim has significantly higher source authority than the other,
    automatically supersede the lower-authority claim.

    Args:
        contradiction_id: ID of the contradiction record
        db: Database session

    Returns:
        True if supersession succeeded, False otherwise
    """
    contradiction = (
        db.query(MemoryContradiction)
        .filter(MemoryContradiction.id == contradiction_id)
        .first()
    )

    if not contradiction:
        logger.warning("Contradiction %d not found for auto-supersession", contradiction_id)
        return False

    # Get both claims
    claim_a = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_a_id
    ).first()
    claim_b = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_b_id
    ).first()

    if not claim_a or not claim_b:
        logger.warning("Claims not found for contradiction %d", contradiction_id)
        return False

    # Get source authority weights
    source_a = None
    source_b = None
    if claim_a.source_snapshot_id:
        from app.models.entities import SourceSnapshot
        snapshot_a = db.query(SourceSnapshot).filter(
            SourceSnapshot.id == claim_a.source_snapshot_id
        ).first()
        if snapshot_a:
            snapshot_source_id = getattr(snapshot_a, "source_id", None)
            snapshot_source_key = getattr(snapshot_a, "source_key", None)
            if snapshot_source_id is not None:
                source_a = db.query(LegalSource).filter(
                    LegalSource.id == snapshot_source_id
                ).first()
            elif snapshot_source_key:
                source_key = str(snapshot_source_key)
                source_a = db.query(LegalSource).filter(
                    LegalSource.source_id == source_key
                ).first()
                if source_a is None and source_key.isdigit():
                    source_a = db.query(LegalSource).filter(
                        LegalSource.id == int(source_key)
                    ).first()
    if claim_b.source_snapshot_id:
        from app.models.entities import SourceSnapshot
        snapshot_b = db.query(SourceSnapshot).filter(
            SourceSnapshot.id == claim_b.source_snapshot_id
        ).first()
        if snapshot_b:
            snapshot_source_id = getattr(snapshot_b, "source_id", None)
            snapshot_source_key = getattr(snapshot_b, "source_key", None)
            if snapshot_source_id is not None:
                source_b = db.query(LegalSource).filter(
                    LegalSource.id == snapshot_source_id
                ).first()
            elif snapshot_source_key:
                source_key = str(snapshot_source_key)
                source_b = db.query(LegalSource).filter(
                    LegalSource.source_id == source_key
                ).first()
                if source_b is None and source_key.isdigit():
                    source_b = db.query(LegalSource).filter(
                        LegalSource.id == int(source_key)
                    ).first()

    weight_a = get_source_authority_weight(source_a.source_type if source_a else None)
    weight_b = get_source_authority_weight(source_b.source_type if source_b else None)

    # Only auto-supersede if authority difference is significant (>0.3)
    authority_threshold = 0.3
    if abs(weight_a - weight_b) < authority_threshold:
        logger.info(
            "Authority difference too small for auto-supersesion: %.2f vs %.2f",
            weight_a, weight_b
        )
        return False

    # Determine which claim to supersede (lower authority)
    if weight_a > weight_b:
        claim_to_supersede = claim_b
        retained_claim = claim_a
    else:
        claim_to_supersede = claim_a
        retained_claim = claim_b

    # Supersede the lower-authority claim
    claim_to_supersede.status = "superseded"
    claim_to_supersede.is_active = False
    max_auth = max(weight_a, weight_b)
    min_auth = min(weight_a, weight_b)
    claim_to_supersede.invalidation_reason = (
        f"Auto-superseded by higher-authority claim {retained_claim.id} "
        f"(authority: {max_auth:.2f} vs {min_auth:.2f})"
    )
    claim_to_supersede.invalidated_at = datetime.now(timezone.utc)
    claim_to_supersede.superseded_by_claim_id = retained_claim.id

    # Mark contradiction as resolved
    contradiction.status = "resolved"
    contradiction.resolved_at = datetime.now(timezone.utc)
    contradiction.resolution_note = "Auto-resolved by authority-based supersession"

    db.commit()
    logger.info(
        "Auto-superseded claim %d by claim %d (authority: %.2f vs %.2f)",
        claim_to_supersede.id,
        retained_claim.id,
        weight_a,
        weight_b,
    )

    return True


def get_open_contradictions_by_claim(
    claim_id: int, db: Session
) -> List[MemoryContradiction]:
    """Get open contradictions for a specific claim.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        List of open MemoryContradiction records
    """
    contradictions = (
        db.query(MemoryContradiction)
        .filter(
            (MemoryContradiction.claim_a_id == claim_id)
            | (MemoryContradiction.claim_b_id == claim_id),
            MemoryContradiction.status == "open",
        )
        .all()
    )
    return contradictions


def get_open_contradictions_by_entity(
    entity_id: int, db: Session
) -> List[MemoryContradiction]:
    """Get open contradictions for all claims on an entity.

    Args:
        entity_id: ID of the entity
        db: Database session

    Returns:
        List of open MemoryContradiction records
    """
    # Get all claims for the entity
    claim_ids = (
        db.query(MemoryClaim.id)
        .filter(MemoryClaim.entity_id == entity_id)
        .all()
    )
    claim_ids = [c[0] for c in claim_ids]

    if not claim_ids:
        return []

    # Get contradictions involving these claims
    contradictions = (
        db.query(MemoryContradiction)
        .filter(
            (MemoryContradiction.claim_a_id.in_(claim_ids))
            | (MemoryContradiction.claim_b_id.in_(claim_ids)),
            MemoryContradiction.status == "open",
        )
        .all()
    )
    return contradictions


def resolve_contradiction_record(
    contradiction_id: int,
    status: str,
    reviewer_id: int,
    resolution_note: str,
    db: Session,
) -> bool:
    """Resolve a contradiction record with reviewer action.

    Args:
        contradiction_id: ID of the contradiction record
        status: New status (resolved, false_positive, ignored)
        reviewer_id: ID of the reviewer
        resolution_note: Optional note about the resolution
        db: Database session

    Returns:
        True if resolution succeeded, False otherwise
    """
    contradiction = (
        db.query(MemoryContradiction)
        .filter(MemoryContradiction.id == contradiction_id)
        .first()
    )

    if not contradiction:
        logger.warning("Contradiction %d not found for resolution", contradiction_id)
        return False

    contradiction.status = status
    # Only set resolved_at for actual resolutions, not ignored
    if status != "ignored":
        contradiction.resolved_at = datetime.now(timezone.utc)
    contradiction.reviewer_id = reviewer_id
    contradiction.resolution_note = resolution_note
    contradiction.updated_at = datetime.now(timezone.utc)

    # Decrement contradiction counts on both claims
    claim_a = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_a_id
    ).first()
    claim_b = db.query(MemoryClaim).filter(
        MemoryClaim.id == contradiction.claim_b_id
    ).first()

    if claim_a and claim_a.contradiction_count > 0:
        claim_a.contradiction_count -= 1
    if claim_b and claim_b.contradiction_count > 0:
        claim_b.contradiction_count -= 1

    db.commit()
    logger.info(
        "Resolved contradiction record %d with status: %s by reviewer %d",
        contradiction_id,
        status,
        reviewer_id,
    )

    return True


# ---------------------------------------------------------------------------
# Contradiction-priority dedupe helpers
# ---------------------------------------------------------------------------

# Severity rank — higher value = higher priority.
_SEVERITY_RANK: Dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def get_contradictions_for_claim_pair(
    claim_a_id: int, claim_b_id: int, db: Session
) -> List[MemoryContradiction]:
    """Return all contradiction records for a claim pair regardless of direction or type.

    Args:
        claim_a_id: One claim in the pair.
        claim_b_id: The other claim in the pair.
        db: Database session.

    Returns:
        All MemoryContradiction records that involve both claims.
    """
    return (
        db.query(MemoryContradiction)
        .filter(
            (
                (MemoryContradiction.claim_a_id == claim_a_id)
                & (MemoryContradiction.claim_b_id == claim_b_id)
            )
            | (
                (MemoryContradiction.claim_a_id == claim_b_id)
                & (MemoryContradiction.claim_b_id == claim_a_id)
            )
        )
        .all()
    )


def select_canonical_contradiction(
    contradictions: List[MemoryContradiction],
) -> Optional[MemoryContradiction]:
    """Pick the highest-priority contradiction from a list.

    Priority order (descending):
      1. Severity rank  (critical > high > medium > low)
      2. Source authority weight (higher is better)
      3. Detected-at timestamp  (most recent wins)

    Args:
        contradictions: Non-empty list of contradiction records for the same pair.

    Returns:
        The canonical MemoryContradiction, or None if the list is empty.
    """
    if not contradictions:
        return None

    def _sort_key(c: MemoryContradiction):
        return (
            _SEVERITY_RANK.get(c.severity or "low", 1),
            c.source_authority_weight or 0.0,
            c.detected_at or datetime.min.replace(tzinfo=timezone.utc),
        )

    return max(contradictions, key=_sort_key)


def dedupe_contradictions_for_entity(entity_id: int, db: Session) -> int:
    """Consolidate duplicate contradiction records for all claim pairs on an entity.

    For every (claim_a, claim_b) pair that has more than one open contradiction
    record, selects the canonical record (highest severity → authority → recency)
    and marks the rest as ``false_positive`` with a ``superseded_by_canonical``
    resolution note.

    Already-closed records (resolved / false_positive / ignored) are left untouched.

    Args:
        entity_id: Entity whose claim-pair contradictions should be deduped.
        db: Database session.

    Returns:
        Number of non-canonical contradiction records that were demoted.
    """
    claim_ids = [
        cid
        for (cid,) in db.query(MemoryClaim.id)
        .filter(MemoryClaim.entity_id == entity_id)
        .all()
    ]
    if not claim_ids:
        return 0

    all_contradictions: List[MemoryContradiction] = (
        db.query(MemoryContradiction)
        .filter(
            or_(
                MemoryContradiction.claim_a_id.in_(claim_ids),
                MemoryContradiction.claim_b_id.in_(claim_ids),
            )
        )
        .all()
    )

    # Group by normalised pair key so direction does not matter.
    pairs: Dict[tuple, List[MemoryContradiction]] = defaultdict(list)
    for c in all_contradictions:
        key = (min(c.claim_a_id, c.claim_b_id), max(c.claim_a_id, c.claim_b_id))
        pairs[key].append(c)

    demoted_count = 0
    now = datetime.now(timezone.utc)

    for pair_contradictions in pairs.values():
        if len(pair_contradictions) <= 1:
            continue

        canonical = select_canonical_contradiction(pair_contradictions)
        if canonical is None:
            continue

        for c in pair_contradictions:
            if c.id == canonical.id:
                continue
            if c.status in ("resolved", "false_positive", "ignored"):
                continue  # Already closed — leave it.
            c.status = "false_positive"
            c.resolution_note = f"superseded_by_canonical:{canonical.id}"
            c.resolved_at = now
            demoted_count += 1

    if demoted_count:
        db.commit()

    logger.info(
        "dedupe_contradictions_for_entity(entity_id=%d): demoted %d records",
        entity_id,
        demoted_count,
    )
    return demoted_count


# ---------------------------------------------------------------------------
# Temporal as-of query
# ---------------------------------------------------------------------------


def query_claims_as_of(
    entity_id: int,
    as_of: datetime,
    db: Session,
    predicate: Optional[str] = None,
) -> List[MemoryClaim]:
    """Return a point-in-time snapshot of active claims for an entity.

    A claim is considered valid *as of* ``as_of`` when:

    * ``valid_from`` is NULL  **or**  ``valid_from <= as_of``   (claim has started)
    * ``valid_to``   is NULL  **or**  ``valid_to  >  as_of``    (claim has not yet ended)
    * ``is_active`` is True

    Claims with status other than ``active`` are excluded by default so the
    snapshot reflects only the currently-trusted knowledge state.

    Args:
        entity_id: Entity to query.
        as_of: Point-in-time reference (timezone-aware recommended).
        db: Database session.
        predicate: Optional predicate filter (e.g. ``"case_status"``).

    Returns:
        List of MemoryClaim records valid at ``as_of``.
    """
    q = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
            MemoryClaim.status == "active",
            or_(MemoryClaim.valid_from.is_(None), MemoryClaim.valid_from <= as_of),
            or_(MemoryClaim.valid_to.is_(None), MemoryClaim.valid_to > as_of),
        )
    )
    if predicate is not None:
        q = q.filter(MemoryClaim.predicate == predicate)
    return q.all()
