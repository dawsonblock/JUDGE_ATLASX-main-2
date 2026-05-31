"""Confidence scoring module for claim confidence calculation.

Implements confidence scoring based on source quality, evidence corroboration,
contradiction penalty, and extraction model reliability.
"""

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.entities import (
    MemoryClaim,
    MemoryEvidenceLink,
    SourceSnapshot,
    SourceRegistry,
)

logger = logging.getLogger(__name__)

# Source quality weights
SOURCE_QUALITY_WEIGHTS = {
    "primary": 0.9,
    "official": 0.8,
    "verified": 0.7,
    "reliable": 0.6,
    "unverified": 0.3,
    "unreliable": 0.1,
}

# Extraction model reliability weights
EXTRACTION_MODEL_WEIGHTS = {
    "human_verified": 1.0,
    "gpt4_turbo": 0.8,
    "gpt4": 0.75,
    "claude_opus": 0.85,
    "claude_sonnet": 0.7,
    "legacy": 0.5,
    "unknown": 0.5,
}


def _get_snapshot_source_quality(
    snapshot: SourceSnapshot | None, db: Session, default: str = "unknown"
) -> str:
    """Safely retrieve source quality from snapshot with multiple fallbacks.
    
    Args:
        snapshot: The SourceSnapshot object
        db: Database session
        default: Default quality if none found
        
    Returns:
        Source quality string (e.g., "primary", "official", "verified", etc.)
    """
    if snapshot is None:
        return default
    
    # 1. Optional backward compatibility for old objects/tests with source_quality
    value = getattr(snapshot, "source_quality", None)
    if value:
        return str(value).lower()
    
    # 2. Try linked source registry via source_key
    if snapshot.source_key:
        source = (
            db.query(SourceRegistry)
            .filter(SourceRegistry.source_key == snapshot.source_key)
            .first()
        )
        if source is not None:
            # Check source_tier which is the new canonical field
            value = (
                getattr(source, "source_tier", None)
                or getattr(source, "source_quality", None)
                or getattr(source, "reliability_score", None)
            )
            if value:
                return str(value).lower()
    
    # 3. Check metadata fields if they exist
    metadata = (
        getattr(snapshot, "metadata", None)
        or getattr(snapshot, "meta", None)
        or {}
    )

    # 3a. Legacy compatibility: some snapshots persist quality in headers_json.
    if not metadata:
        headers_json = getattr(snapshot, "headers_json", None)
        if isinstance(headers_json, str) and headers_json.strip().startswith("{"):
            try:
                parsed = json.loads(headers_json)
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError:
                metadata = {}

    if isinstance(metadata, dict):
        value = (
            metadata.get("source_quality")
            or metadata.get("source_tier")
            or metadata.get("authority_score")
        )
        if value:
            return str(value).lower()
    
    return default


def calculate_claim_confidence(claim_id: int, db: Session) -> float:
    """Calculate confidence score for a claim.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        Calculated confidence score (0.0-1.0)
    """
    claim = db.query(MemoryClaim).filter(MemoryClaim.id == claim_id).first()
    if not claim:
        logger.warning("Claim %d not found for confidence calculation", claim_id)
        return 0.0

    # Base score from source quality
    source_quality_score = _get_source_quality_score(claim_id, db)

    # Corroboration bonus
    corroboration_bonus = _get_corroboration_bonus(claim_id, db)

    # Contradiction penalty
    contradiction_penalty = _get_contradiction_penalty(claim, db)

    # Extraction model reliability
    model_reliability = _get_model_reliability(claim.extraction_model)

    # Calculate weighted score
    base_score = (source_quality_score * 0.7) + (model_reliability * 0.3)
    adjusted_score = base_score + corroboration_bonus - contradiction_penalty

    # Clamp to valid range
    final_score = max(0.0, min(1.0, adjusted_score))

    logger.debug(
        "Calculated confidence for claim %d: %.2f "
        "(source=%.2f, corroboration=%.2f, contradiction=%.2f, model=%.2f)",
        claim_id,
        final_score,
        source_quality_score,
        corroboration_bonus,
        contradiction_penalty,
        model_reliability,
    )

    return final_score


def _get_source_quality_score(claim_id: int, db: Session) -> float:
    """Get source quality score based on linked evidence.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        Source quality score (0.0-1.0)
    """
    evidence_links = (
        db.query(MemoryEvidenceLink)
        .filter(MemoryEvidenceLink.claim_id == claim_id)
        .all()
    )

    if not evidence_links:
        return 0.5  # Default for claims without evidence

    total_score = 0.0
    for link in evidence_links:
        snapshot = (
            db.query(SourceSnapshot)
            .filter(SourceSnapshot.id == link.snapshot_id)
            .first()
        )
        quality_score = 0.5
        if snapshot:
            quality = _get_snapshot_source_quality(snapshot, db)
            quality_score = SOURCE_QUALITY_WEIGHTS.get(quality, 0.5)

        # Blend source quality with per-link evidence confidence so high-quality
        # evidence can meaningfully increase claim confidence.
        evidence_score = link.confidence if link.confidence is not None else 0.5
        total_score += (quality_score * 0.3) + (evidence_score * 0.7)

    # Average score from all evidence
    avg_score = total_score / len(evidence_links) if evidence_links else 0.5
    return min(1.0, avg_score)


def _get_corroboration_bonus(claim_id: int, db: Session) -> float:
    """Get corroboration bonus based on supporting evidence count.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        Corroboration bonus (0.0-0.2)
    """
    supporting_count = (
        db.query(MemoryEvidenceLink)
        .filter(
            MemoryEvidenceLink.claim_id == claim_id,
            MemoryEvidenceLink.support_type == "supports",
        )
        .count()
    )

    # Bonus caps at 0.2 for 5+ supporting sources
    if supporting_count == 0:
        return -0.1  # Penalty for no supporting evidence
    elif supporting_count == 1:
        return 0.0
    elif supporting_count == 2:
        return 0.05
    elif supporting_count == 3:
        return 0.1
    elif supporting_count == 4:
        return 0.15
    else:
        return 0.2


def _get_contradiction_penalty(claim: MemoryClaim, db: Session) -> float:
    """Get contradiction penalty based on conflicting claims.

    Args:
        claim: The claim to evaluate
        db: Database session

    Returns:
        Contradiction penalty (0.0-0.3)
    """
    # Use the contradiction_count field from the claim
    contradiction_count = claim.contradiction_count or 0

    # Penalty increases with number of contradictions
    if contradiction_count == 0:
        return 0.0
    elif contradiction_count == 1:
        return 0.1
    elif contradiction_count == 2:
        return 0.2
    else:
        return 0.3


def _get_model_reliability(extraction_model: Optional[str]) -> float:
    """Get extraction model reliability score.

    Args:
        extraction_model: Name of the extraction model

    Returns:
        Model reliability score (0.0-1.0)
    """
    if not extraction_model:
        return EXTRACTION_MODEL_WEIGHTS["unknown"]

    model_lower = extraction_model.lower()
    return EXTRACTION_MODEL_WEIGHTS.get(model_lower, 0.5)


def recalculate_claim_confidence(claim_id: int, db: Session) -> bool:
    """Recalculate and update confidence for a claim.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        True if update succeeded, False otherwise
    """
    claim = db.query(MemoryClaim).filter(MemoryClaim.id == claim_id).first()
    if not claim:
        logger.warning("Claim %d not found for confidence recalculation", claim_id)
        return False

    new_confidence = calculate_claim_confidence(claim_id, db)
    claim.confidence = new_confidence
    db.commit()

    logger.info("Recalculated confidence for claim %d: %.2f", claim_id, new_confidence)
    return True


def batch_recalculate_confidence(entity_id: int, db: Session) -> int:
    """Recalculate confidence for all claims on an entity.

    Args:
        entity_id: ID of the entity
        db: Database session

    Returns:
        Number of claims updated
    """
    claims = (
        db.query(MemoryClaim)
        .filter(MemoryClaim.entity_id == entity_id)
        .all()
    )

    updated_count = 0
    for claim in claims:
        if recalculate_claim_confidence(claim.id, db):
            updated_count += 1

    logger.info("Recalculated confidence for %d claims on entity %d", updated_count, entity_id)
    return updated_count
