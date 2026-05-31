"""Final data flow target validation (Phase 23).

Validates data flow architecture and integrity.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.ingestion.statuses import COMPLETED

logger = logging.getLogger(__name__)


class DataFlowValidator:
    """Validates data flow integrity across the system."""

    def __init__(self, db: Session):
        self.db = db

    def validate_ingestion_to_memory_flow(self) -> Dict[str, Any]:
        """Validate ingestion to memory data flow.

        Returns:
            Validation result
        """
        # Check that ingestion runs produce memory claims
        from app.models.entities import IngestionRun, MemoryClaim

        recent_runs = (
            self.db.query(IngestionRun)
            .order_by(IngestionRun.id.desc())
            .limit(10)
            .all()
        )

        valid = True
        issues = []

        for run in recent_runs:
            if run.persisted_count == 0 and run.status == COMPLETED:
                issues.append(f"Run {run.id} completed with no persisted records")
                valid = False

        return {
            "component": "ingestion_to_memory",
            "valid": valid,
            "issues": issues,
            "sample_runs_checked": len(recent_runs),
        }

    def validate_memory_to_evidence_flow(self) -> Dict[str, Any]:
        """Validate memory to evidence data flow.

        Returns:
            Validation result
        """
        from app.models.entities import MemoryClaim, MemoryEvidenceLink

        # Check that claims have evidence links
        claims_without_evidence = (
            self.db.query(MemoryClaim)
            .filter(MemoryClaim.review_status == "approved")
            .all()
        )

        missing_evidence = []
        for claim in claims_without_evidence:
            link_count = (
                self.db.query(MemoryEvidenceLink)
                .filter_by(claim_id=claim.id)
                .count()
            )
            if link_count == 0:
                missing_evidence.append(claim.id)

        valid = len(missing_evidence) == 0

        return {
            "component": "memory_to_evidence",
            "valid": valid,
            "issues": [f"Claim {cid} missing evidence" for cid in missing_evidence],
            "claims_checked": len(claims_without_evidence),
        }

    def validate_evidence_to_publication_flow(self) -> Dict[str, Any]:
        """Validate evidence to publication data flow.

        Returns:
            Validation result
        """
        from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot

        # Check that evidence links have valid snapshots
        broken_links = (
            self.db.query(MemoryEvidenceLink)
            .outerjoin(SourceSnapshot, MemoryEvidenceLink.snapshot_id == SourceSnapshot.id)
            .filter(SourceSnapshot.id.is_(None))
            .all()
        )

        valid = len(broken_links) == 0

        return {
            "component": "evidence_to_publication",
            "valid": valid,
            "issues": [f"Broken link {link.id}" for link in broken_links],
            "links_checked": len(broken_links),
        }

    def validate_review_to_publication_flow(self) -> Dict[str, Any]:
        """Validate review to publication data flow.

        Returns:
            Validation result
        """
        from app.models.entities import MemoryClaim, EvidenceReview

        # Check that published items have review records
        published_without_review = []
        published_claims = (
            self.db.query(MemoryClaim)
            .filter(MemoryClaim.review_status == "approved")
            .all()
        )

        for claim in published_claims:
            has_review = (
                self.db.query(EvidenceReview)
                .filter_by(entity_id=claim.id, entity_type="memory_claim")
                .first()
            )
            if not has_review:
                published_without_review.append(claim.id)

        valid = len(published_without_review) == 0

        return {
            "component": "review_to_publication",
            "valid": valid,
            "issues": [f"Published claim {cid} missing review" for cid in published_without_review],
            "claims_checked": len(published_claims),
        }

    def run_full_validation(self) -> Dict[str, Any]:
        """Run all data flow validations.

        Returns:
            Combined validation results
        """
        results = {
            "ingestion_to_memory": self.validate_ingestion_to_memory_flow(),
            "memory_to_evidence": self.validate_memory_to_evidence_flow(),
            "evidence_to_publication": self.validate_evidence_to_publication_flow(),
            "review_to_publication": self.validate_review_to_publication_flow(),
        }

        # Overall validity
        all_valid = all(r["valid"] for r in results.values())
        total_issues = sum(len(r["issues"]) for r in results.values())

        results["overall_valid"] = all_valid
        results["total_issues"] = total_issues

        return results


def validate_data_flow(db: Session) -> Dict[str, Any]:
    """Validate complete data flow.

    Args:
        db: Database session

    Returns:
        Validation results
    """
    validator = DataFlowValidator(db)
    return validator.run_full_validation()
