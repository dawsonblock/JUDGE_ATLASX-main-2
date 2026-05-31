"""Claim evidence link module for evidence governance.

Implements validation for evidence links between claims and source snapshots.
"""

import hashlib
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot

logger = logging.getLogger(__name__)


def validate_public_claim_has_evidence(claim_id: int, db: Session) -> bool:
    """Validate that a public claim has at least one supporting evidence link.

    Args:
        claim_id: ID of the claim to validate
        db: Database session

    Returns:
        True if claim has supporting evidence, False otherwise
    """
    claim = db.query(MemoryClaim).filter(MemoryClaim.id == claim_id).first()
    if not claim:
        logger.warning("Claim %d not found for evidence validation", claim_id)
        return False

    # Only validate public claims
    if claim.status != "public":
        return True

    # Check for supporting evidence links
    supporting_links = (
        db.query(MemoryEvidenceLink)
        .filter(
            MemoryEvidenceLink.claim_id == claim_id,
            MemoryEvidenceLink.support_type == "supports",
        )
        .count()
    )

    if supporting_links == 0:
        logger.warning(
            "Public claim %d has no supporting evidence links", claim_id
        )
        return False

    return True


def detect_orphan_evidence_links(db: Session) -> list[MemoryEvidenceLink]:
    """Detect evidence links that reference non-existent claims or snapshots.

    Args:
        db: Database session

    Returns:
        List of orphan evidence links
    """
    orphan_links = []

    # Check for links with non-existent claims
    all_links = db.query(MemoryEvidenceLink).all()
    for link in all_links:
        claim_exists = (
            db.query(MemoryClaim)
            .filter(MemoryClaim.id == link.claim_id)
            .first()
            is not None
        )
        snapshot_exists = (
            db.query(SourceSnapshot)
            .filter(SourceSnapshot.id == link.snapshot_id)
            .first()
            is not None
        )

        if not claim_exists or not snapshot_exists:
            orphan_links.append(link)
            logger.warning(
                "Orphan evidence link %d references claim %d (exists: %s) "
                "and snapshot %d (exists: %s)",
                link.id,
                link.claim_id,
                claim_exists,
                link.snapshot_id,
                snapshot_exists,
            )

    return orphan_links


def create_evidence_link(
    claim_id: int,
    snapshot_id: int,
    support_type: str,
    quote_text: Optional[str] = None,
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
    page_number: Optional[int] = None,
    confidence: float = 0.0,
    db: Optional[Session] = None,
) -> MemoryEvidenceLink:
    """Create a new evidence link with validation.

    Args:
        claim_id: ID of the claim
        snapshot_id: ID of the source snapshot
        support_type: Type of support (supports, contradicts, mentions, context, supersedes)
        quote_text: Evidence quote text
        char_start: Character offset start
        char_end: Character offset end
        page_number: Source page number
        confidence: Evidence confidence score (0.0-1.0)
        db: Database session

    Returns:
        Created MemoryEvidenceLink

    Raises:
        ValueError: If validation fails
    """
    # Validate support_type
    valid_support_types = [
        "supports",
        "contradicts",
        "mentions",
        "context",
        "supersedes",
    ]
    if support_type not in valid_support_types:
        raise ValueError(
            f"Invalid support_type: {support_type}. "
            f"Must be one of: {valid_support_types}"
        )

    # Validate confidence range
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"Confidence must be between 0.0 and 1.0, got {confidence}"
        )

    # Validate character offsets
    if char_start is not None and char_end is not None:
        if char_start < 0 or char_end < 0:
            raise ValueError(
                f"Character offsets must be non-negative, got start={char_start}, end={char_end}"
            )
        if char_start > char_end:
            raise ValueError(
                f"Character start must be <= end, got start={char_start}, end={char_end}"
            )

    # Create evidence link
    checksum_payload = f"{claim_id}:{snapshot_id}:{support_type}:{quote_text or ''}:{char_start}:{char_end}:{page_number}".encode("utf-8")
    evidence_checksum = hashlib.sha256(checksum_payload).hexdigest()

    link = MemoryEvidenceLink(
        claim_id=claim_id,
        snapshot_id=snapshot_id,
        evidence_checksum=evidence_checksum,
        support_type=support_type,
        quote_text=quote_text,
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        confidence=confidence,
    )

    if db:
        db.add(link)
        db.commit()
        db.refresh(link)

    logger.info(
        "Created evidence link %d for claim %d from snapshot %d "
        "(support_type=%s, confidence=%f)",
        link.id,
        claim_id,
        snapshot_id,
        support_type,
        confidence,
    )

    return link
