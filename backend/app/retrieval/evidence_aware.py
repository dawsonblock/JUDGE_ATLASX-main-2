"""Evidence-aware retrieval for claims and entities.

Provides retrieval that considers evidence quality, confidence, and relevance.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot

logger = logging.getLogger(__name__)


def _get_snapshot_source_quality(snapshot: SourceSnapshot) -> str:
    """Resolve source quality from current or legacy SourceSnapshot storage."""
    quality = getattr(snapshot, "source_quality", None)
    if quality:
        return str(quality).lower()

    headers_json = getattr(snapshot, "headers_json", None)
    if headers_json:
        try:
            parsed = json.loads(headers_json)
            if isinstance(parsed, dict) and parsed.get("source_quality"):
                return str(parsed["source_quality"]).lower()
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.debug("Invalid headers_json for snapshot quality", exc_info=True)

    return "unknown"


def retrieve_claims_with_evidence(
    entity_id: int,
    db: Session,
    min_confidence: float = 0.5,
    require_supporting_evidence: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieve claims for an entity with evidence information.

    Args:
        entity_id: Entity ID to retrieve claims for
        db: Database session
        min_confidence: Minimum confidence threshold
        require_supporting_evidence: Require at least one supporting evidence link
        limit: Maximum number of claims to return

    Returns:
        List of claims with evidence information
    """
    query = db.query(MemoryClaim).filter(
        MemoryClaim.entity_id == entity_id,
        MemoryClaim.confidence >= min_confidence,
        MemoryClaim.is_active == True,
    )

    claims = query.limit(limit).all()

    results = []
    for claim in claims:
        # Get evidence links
        evidence_links = (
            db.query(MemoryEvidenceLink)
            .filter(MemoryEvidenceLink.claim_id == claim.id)
            .all()
        )

        # Filter if supporting evidence is required
        if require_supporting_evidence:
            supporting = [e for e in evidence_links if e.support_type == "supports"]
            if not supporting:
                continue

        # Calculate evidence score
        evidence_score = _calculate_evidence_score(evidence_links)

        results.append(
            {
                "claim_id": claim.id,
                "claim_key": claim.claim_key,
                "claim_type": claim.claim_type,
                "claim_value": claim.claim_value,
                "confidence": claim.confidence,
                "evidence_count": len(evidence_links),
                "supporting_count": sum(1 for e in evidence_links if e.support_type == "supports"),
                "contradicting_count": sum(1 for e in evidence_links if e.support_type == "contradicts"),
                "evidence_score": evidence_score,
                "review_status": claim.review_status,
            }
        )

    # Sort by evidence score descending
    results.sort(key=lambda x: x["evidence_score"], reverse=True)

    return results


def filter_evidence_by_quality(
    evidence_links: List[MemoryEvidenceLink],
    db: Session,
    min_source_quality: str = "court_record",
    min_evidence_confidence: float = 0.5,
) -> List[MemoryEvidenceLink]:
    """Filter evidence links by quality thresholds.

    Args:
        evidence_links: List of evidence links to filter
        db: Database session
        min_source_quality: Minimum source quality tier
        min_evidence_confidence: Minimum evidence confidence

    Returns:
        Filtered list of evidence links
    """
    quality_rank = {"court_record": 3, "official_gov": 2, "news_only_context": 1}
    min_rank = quality_rank.get(min_source_quality, 0)

    filtered = []
    for link in evidence_links:
        # Check evidence confidence
        if link.confidence and link.confidence < min_evidence_confidence:
            continue

        # Check source quality
        snapshot = db.query(SourceSnapshot).filter_by(id=link.snapshot_id).first()
        if not snapshot:
            continue

        source_rank = quality_rank.get(_get_snapshot_source_quality(snapshot), 0)
        if source_rank < min_rank:
            continue

        filtered.append(link)

    return filtered


def rank_evidence_by_relevance(
    evidence_links: List[MemoryEvidenceLink],
    claim: MemoryClaim,
    db: Session,
) -> List[MemoryEvidenceLink]:
    """Rank evidence links by relevance to the claim.

    Args:
        evidence_links: List of evidence links to rank
        claim: Claim to rank against
        db: Database session

    Returns:
        Ranked list of evidence links
    """
    scored = []
    for link in evidence_links:
        score = _calculate_relevance_score(link, claim, db)
        scored.append((score, link))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [link for _, link in scored]


def _calculate_evidence_score(evidence_links: List[MemoryEvidenceLink]) -> float:
    """Calculate overall evidence score for a claim.

    Args:
        evidence_links: List of evidence links

    Returns:
        Evidence score between 0.0 and 1.0
    """
    if not evidence_links:
        return 0.0

    supporting = sum(1 for e in evidence_links if e.support_type == "supports")
    contradicting = sum(1 for e in evidence_links if e.support_type == "contradicts")
    total = len(evidence_links)

    if total == 0:
        return 0.0

    # Base score from supporting vs total
    base_score = supporting / total

    # Average evidence confidence
    confidences = [e.confidence for e in evidence_links if e.confidence is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

    # Combine scores
    final_score = 0.7 * base_score + 0.3 * avg_confidence

    return max(0.0, min(1.0, final_score))


def _calculate_relevance_score(
    link: MemoryEvidenceLink,
    claim: MemoryClaim,
    db: Session,
) -> float:
    """Calculate relevance score of evidence to claim.

    Args:
        link: Evidence link
        claim: Claim
        db: Database session

    Returns:
        Relevance score between 0.0 and 1.0
    """
    score = 0.0

    # Support type score
    if link.support_type == "supports":
        score += 0.5
    elif link.support_type == "contradicts":
        score -= 0.5

    # Evidence confidence
    if link.confidence:
        score += 0.3 * link.confidence

    # Source quality
    snapshot = db.query(SourceSnapshot).filter_by(id=link.snapshot_id).first()
    if snapshot:
        quality_rank = {"court_record": 0.3, "official_gov": 0.2, "news_only_context": 0.1}
        score += quality_rank.get(_get_snapshot_source_quality(snapshot), 0.0)

    # Quote match bonus
    if link.quote_text and claim.claim_value:
        if claim.claim_value.lower() in link.quote_text.lower():
            score += 0.2

    return max(0.0, min(1.0, score))


def get_evidence_summary(
    claim_id: int,
    db: Session,
) -> Dict[str, Any]:
    """Get summary of evidence for a claim.

    Args:
        claim_id: Claim ID
        db: Database session

    Returns:
        Evidence summary dictionary
    """
    evidence_links = (
        db.query(MemoryEvidenceLink)
        .filter(MemoryEvidenceLink.claim_id == claim_id)
        .all()
    )

    supporting = [e for e in evidence_links if e.support_type == "supports"]
    contradicting = [e for e in evidence_links if e.support_type == "contradicts"]
    neutral = [e for e in evidence_links if e.support_type == "neutral"]

    return {
        "total_evidence": len(evidence_links),
        "supporting_count": len(supporting),
        "contradicting_count": len(contradicting),
        "neutral_count": len(neutral),
        "evidence_score": _calculate_evidence_score(evidence_links),
        "avg_evidence_confidence": (
            sum(e.confidence for e in evidence_links if e.confidence) / len(evidence_links)
            if evidence_links
            else 0.0
        ),
    }
