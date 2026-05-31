"""Service for managing relationship evidence.

Provides methods for creating, querying, and verifying evidence
that supports entity relationships in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.entities import RelationshipEvidence

if TYPE_CHECKING:
    pass


@dataclass
class EvidenceSummary:
    """Summary of evidence for a relationship."""

    evidence_id: int
    relationship_type: str
    evidence_type: str
    evidence_source: str
    confidence: float
    is_verified: bool
    excerpt_preview: str | None


class RelationshipEvidenceService:
    """Service for managing relationship evidence."""

    # Minimum confidence threshold requiring manual verification
    VERIFICATION_THRESHOLD = 0.6

    def __init__(self, db: Session):
        self.db = db

    def create_evidence(
        self,
        from_entity_type: str,
        from_entity_id: int,
        to_entity_type: str,
        to_entity_id: int,
        relationship_type: str,
        evidence_type: str,
        evidence_source: str,
        evidence_excerpt: str | None = None,
        evidence_location: str | None = None,
        evidence_snapshot_id: int | None = None,
        extracted_by: str = "system",
        confidence: float = 0.5,
        commit: bool = True,
    ) -> RelationshipEvidence:
        """Create new relationship evidence.

        Args:
            from_entity_type: Source entity type
            from_entity_id: Source entity ID
            to_entity_type: Target entity type
            to_entity_id: Target entity ID
            relationship_type: Type of relationship being evidenced
            evidence_type: Type of evidence (docket_text, police_report, etc.)
            evidence_source: Source registry key
            evidence_excerpt: Text excerpt supporting the link
            evidence_location: Location in document (page, paragraph)
            evidence_snapshot_id: Optional snapshot ID
            extracted_by: Who/what extracted this evidence
            confidence: Confidence score (0.0-1.0)

        Returns:
            Created RelationshipEvidence record
        """
        evidence = RelationshipEvidence(
            from_entity_type=from_entity_type,
            from_entity_id=from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=to_entity_id,
            relationship_type=relationship_type,
            evidence_type=evidence_type,
            evidence_source=evidence_source,
            evidence_excerpt=evidence_excerpt,
            evidence_location=evidence_location,
            evidence_snapshot_id=evidence_snapshot_id,
            extracted_by=extracted_by,
            confidence=confidence,
            verified_by=None,
            verified_at=None,
        )
        self.db.add(evidence)
        self.db.flush()
        if commit:
            self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def get_evidence_for_relationship(
        self,
        from_entity_type: str,
        from_entity_id: int,
        to_entity_type: str,
        to_entity_id: int,
        limit: int = 10,
    ) -> list[EvidenceSummary]:
        """Get all evidence for a specific relationship.

        Args:
            from_entity_type: Source entity type
            from_entity_id: Source entity ID
            to_entity_type: Target entity type
            to_entity_id: Target entity ID
            limit: Maximum results

        Returns:
            List of evidence summaries
        """
        evidences = (
            self.db.query(RelationshipEvidence)
            .filter(
                RelationshipEvidence.from_entity_type == from_entity_type,
                RelationshipEvidence.from_entity_id == from_entity_id,
                RelationshipEvidence.to_entity_type == to_entity_type,
                RelationshipEvidence.to_entity_id == to_entity_id,
            )
            .order_by(desc(RelationshipEvidence.confidence))
            .limit(limit)
            .all()
        )

        return [
            EvidenceSummary(
                evidence_id=e.id,
                relationship_type=e.relationship_type,
                evidence_type=e.evidence_type,
                evidence_source=e.evidence_source,
                confidence=e.confidence,
                is_verified=e.verified_by is not None,
                excerpt_preview=(
                    e.evidence_excerpt[:200] + "..."
                    if e.evidence_excerpt and len(e.evidence_excerpt) > 200
                    else e.evidence_excerpt
                ),
            )
            for e in evidences
        ]

    def get_evidence_for_entity(
        self,
        entity_type: str,
        entity_id: int,
        as_source: bool = True,
        as_target: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get all evidence involving an entity.

        Args:
            entity_type: Entity type
            entity_id: Entity ID
            as_source: Include where entity is source
            as_target: Include where entity is target
            limit: Maximum results

        Returns:
            List of evidence records with relationship info
        """
        query = self.db.query(RelationshipEvidence)

        if as_source and as_target:
            query = query.filter(
                (
                    (RelationshipEvidence.from_entity_type == entity_type)
                    & (RelationshipEvidence.from_entity_id == entity_id)
                )
                | (
                    (RelationshipEvidence.to_entity_type == entity_type)
                    & (RelationshipEvidence.to_entity_id == entity_id)
                )
            )
        elif as_source:
            query = query.filter(
                (RelationshipEvidence.from_entity_type == entity_type)
                & (RelationshipEvidence.from_entity_id == entity_id)
            )
        elif as_target:
            query = query.filter(
                (RelationshipEvidence.to_entity_type == entity_type)
                & (RelationshipEvidence.to_entity_id == entity_id)
            )
        else:
            return []

        evidences = query.order_by(desc(RelationshipEvidence.confidence)).limit(limit).all()

        return [
            {
                "evidence_id": e.id,
                "relationship_type": e.relationship_type,
                "from_entity_type": e.from_entity_type,
                "from_entity_id": e.from_entity_id,
                "to_entity_type": e.to_entity_type,
                "to_entity_id": e.to_entity_id,
                "evidence_type": e.evidence_type,
                "evidence_source": e.evidence_source,
                "confidence": e.confidence,
                "is_verified": e.verified_by is not None,
                "evidence_excerpt": e.evidence_excerpt,
                "evidence_location": e.evidence_location,
                "extracted_by": e.extracted_by,
                "created_at": e.created_at,
            }
            for e in evidences
        ]

    def verify_evidence(
        self,
        evidence_id: int,
        verified_by: str,
        notes: str | None = None,
        commit: bool = True,
    ) -> RelationshipEvidence | None:
        """Mark evidence as verified by an admin.

        Args:
            evidence_id: Evidence record ID
            verified_by: Admin identifier
            notes: Optional verification notes

        Returns:
            Updated evidence record or None if not found
        """
        evidence = (
            self.db.query(RelationshipEvidence)
            .filter_by(id=evidence_id)
            .first()
        )

        if not evidence:
            return None

        evidence.verified_by = verified_by
        evidence.verified_at = datetime.now(timezone.utc)

        if notes:
            # Append notes to excerpt if provided
            if evidence.evidence_excerpt:
                evidence.evidence_excerpt += f"\n\n[Verification Notes: {notes}]"
            else:
                evidence.evidence_excerpt = f"[Verification Notes: {notes}]"

        self.db.flush()
        if commit:
            self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def unverify_evidence(
        self,
        evidence_id: int,
        reason: str | None = None,
        commit: bool = True,
    ) -> RelationshipEvidence | None:
        """Remove verification from evidence.

        Args:
            evidence_id: Evidence record ID
            reason: Optional reason for unverification

        Returns:
            Updated evidence record or None if not found
        """
        evidence = (
            self.db.query(RelationshipEvidence)
            .filter_by(id=evidence_id)
            .first()
        )

        if not evidence:
            return None

        evidence.verified_by = None
        evidence.verified_at = None

        if reason:
            if evidence.evidence_excerpt:
                evidence.evidence_excerpt += f"\n\n[Unverification Reason: {reason}]"
            else:
                evidence.evidence_excerpt = f"[Unverification Reason: {reason}]"

        self.db.flush()
        if commit:
            self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def requires_verification(self, confidence: float) -> bool:
        """Check if a confidence level requires manual verification.

        Args:
            confidence: Confidence score (0.0-1.0)

        Returns:
            True if verification is required
        """
        return confidence < self.VERIFICATION_THRESHOLD

    def get_unverified_evidence(
        self,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0,
        limit: int = 100,
    ) -> list[RelationshipEvidence]:
        """Get unverified evidence within a confidence range.

        Args:
            min_confidence: Minimum confidence
            max_confidence: Maximum confidence
            limit: Maximum results

        Returns:
            List of unverified evidence records
        """
        return (
            self.db.query(RelationshipEvidence)
            .filter(
                RelationshipEvidence.verified_by.is_(None),
                RelationshipEvidence.confidence >= min_confidence,
                RelationshipEvidence.confidence <= max_confidence,
            )
            .order_by(desc(RelationshipEvidence.confidence))
            .limit(limit)
            .all()
        )
