"""Review-priority system for triaging review tasks.

Implements review-priority tier calculation based on confidence,
contradictions, and evidence.
"""

import logging
from typing import Dict
from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, CanonicalEntity

logger = logging.getLogger(__name__)

# Review-priority thresholds (higher value = higher review priority)
REVIEW_PRIORITY_THRESHOLDS = {
    "critical": 0.85,  # Critical review priority
    "high": 0.65,  # High review priority
    "medium": 0.35,  # Medium review priority
    "low": 0.0,  # Low review priority, may be auto-approved
}

# Review requirements per tier
REVIEW_REQUIREMENTS = {
    "critical": {"requires_review": True, "requires_evidence": True, "auto_approve": False},
    "high": {"requires_review": True, "requires_evidence": True, "auto_approve": False},
    "medium": {"requires_review": True, "requires_evidence": False, "auto_approve": False},
    "low": {"requires_review": False, "requires_evidence": False, "auto_approve": True},
}


def calculate_claim_review_priority_tier(claim_id: int, db: Session) -> str:
    """Calculate review-priority tier for a claim.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        Review-priority tier: critical, high, medium, or low
    """
    claim = db.query(MemoryClaim).filter(MemoryClaim.id == claim_id).first()
    if not claim:
        logger.warning("Claim %d not found for review-priority calculation", claim_id)
        return "high"  # Default to high review priority for unknown claims

    # Base priority value from confidence (lower confidence = higher priority)
    confidence_priority_value = 1.0 - claim.confidence

    # Priority lift from contradictions
    contradiction_priority_value = min(0.5, (claim.contradiction_count or 0) * 0.2)

    # Priority lift from lack of evidence
    evidence_priority_value = 0.0
    if claim.corroboration_count == 0:
        evidence_priority_value = 0.2
    elif claim.corroboration_count == 1:
        evidence_priority_value = 0.1

    # Claim-type sensitivity adjustments
    claim_type_priority_value = 0.0
    claim_type = (claim.claim_type or "").lower()
    if claim_type == "criminal_allegation":
        claim_type_priority_value = 0.45
    elif claim_type in {"case_outcome", "appeal_outcome", "sentence"}:
        claim_type_priority_value = 0.15

    # Calculate total review-priority value
    total_priority_value = (
        confidence_priority_value
        + contradiction_priority_value
        + evidence_priority_value
        + claim_type_priority_value
    )
    total_priority_value = min(1.0, total_priority_value)  # Cap at 1.0

    # Determine tier (higher priority value = higher tier)
    if total_priority_value >= REVIEW_PRIORITY_THRESHOLDS["critical"]:
        tier = "critical"
    elif total_priority_value >= REVIEW_PRIORITY_THRESHOLDS["high"]:
        tier = "high"
    elif total_priority_value >= REVIEW_PRIORITY_THRESHOLDS["medium"]:
        tier = "medium"
    else:
        tier = "low"

    logger.debug(
        "Review-priority tier for claim %d: %s (confidence=%.2f, contradictions=%d, corroboration=%d)",
        claim_id,
        tier,
        claim.confidence,
        claim.contradiction_count,
        claim.corroboration_count,
    )

    return tier


def get_review_requirements(review_priority_tier: str) -> Dict[str, bool]:
    """Get review requirements for a review-priority tier.

    Args:
        review_priority_tier: Review-priority tier (critical, high, medium, low)

    Returns:
        Dictionary with review requirement flags
    """
    return REVIEW_REQUIREMENTS.get(review_priority_tier, REVIEW_REQUIREMENTS["high"])


def can_auto_approve(claim_id: int, db: Session) -> bool:
    """Check if a claim can be auto-approved based on review priority.

    Args:
        claim_id: ID of the claim
        db: Database session

    Returns:
        True if auto-approval is allowed, False otherwise
    """
    review_priority_tier = calculate_claim_review_priority_tier(claim_id, db)
    requirements = get_review_requirements(review_priority_tier)
    return requirements["auto_approve"]


def calculate_entity_review_priority_tier(entity_id: int, db: Session) -> str:
    """Calculate review-priority tier for an entity based on its claims.

    Args:
        entity_id: ID of the entity
        db: Database session

    Returns:
        Review-priority tier: critical, high, medium, or low
    """
    claims = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active == True,
        )
        .all()
    )

    if not claims:
        return "low"

    # Calculate priority tier for each claim
    priority_scores = []
    for claim in claims:
        review_priority_tier = calculate_claim_review_priority_tier(claim.id, db)
        # Convert tier to numeric score aligned with threshold boundaries
        # Use threshold values directly for consistency
        tier_scores = {
            "critical": 1.0,  # Above 0.85
            "high": 0.75,    # Between 0.65 and 0.85
            "medium": 0.5,   # Between 0.35 and 0.65
            "low": 0.175,    # Between 0.0 and 0.35
        }
        priority_scores.append(tier_scores.get(review_priority_tier, 0.75))

    # Entity priority is the maximum of its claims' priority tiers
    max_priority_value = max(priority_scores) if priority_scores else 0.75

    # Convert back to tier (higher priority = higher tier)
    if max_priority_value >= REVIEW_PRIORITY_THRESHOLDS["critical"]:
        return "critical"
    elif max_priority_value >= REVIEW_PRIORITY_THRESHOLDS["high"]:
        return "high"
    elif max_priority_value >= REVIEW_PRIORITY_THRESHOLDS["medium"]:
        return "medium"
    else:
        return "low"


def batch_calculate_review_priority_tiers(entity_id: int, db: Session) -> Dict[int, str]:
    """Calculate review-priority tiers for all claims on an entity.

    Args:
        entity_id: ID of the entity
        db: Database session

    Returns:
        Dictionary mapping claim IDs to review-priority tiers
    """
    claims = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active == True,
        )
        .all()
    )

    review_priority_tiers = {}
    for claim in claims:
        review_priority_tiers[claim.id] = calculate_claim_review_priority_tier(claim.id, db)

    logger.info(
        "Calculated review-priority tiers for %d claims on entity %d",
        len(review_priority_tiers),
        entity_id,
    )
    return review_priority_tiers


# Backward-compatible aliases retained for existing call sites.
RISK_TIERS = REVIEW_PRIORITY_THRESHOLDS


def calculate_claim_risk_tier(claim_id: int, db: Session) -> str:
    return calculate_claim_review_priority_tier(claim_id, db)


def calculate_entity_risk_tier(entity_id: int, db: Session) -> str:
    return calculate_entity_review_priority_tier(entity_id, db)


def batch_calculate_risk_tiers(entity_id: int, db: Session) -> Dict[int, str]:
    return batch_calculate_review_priority_tiers(entity_id, db)
