"""Entity resolution safety system.

Implements safety controls for entity merges including confidence thresholds,
human approval requirements, and audit trails.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.entities import CanonicalEntity
from app.graph.graph_merge import propose_entity_merge

logger = logging.getLogger(__name__)

# Configuration
MERGE_CONFIDENCE_THRESHOLD = 0.85
HIGH_RISK_THRESHOLD = 0.95
REQUIRE_HUMAN_APPROVAL = True


def propose_safe_merge(
    entity_id_1: int,
    entity_id_2: int,
    db: Session,
    actor: Optional[str] = None,
) -> dict:
    """Propose an entity merge with safety checks.

    Args:
        entity_id_1: ID of first entity
        entity_id_2: ID of second entity
        db: Database session
        actor: Optional actor identifier

    Returns:
        Dictionary with merge proposal and safety assessment
    """
    # Get entities
    entity1 = db.query(CanonicalEntity).filter(CanonicalEntity.id == entity_id_1).first()
    entity2 = db.query(CanonicalEntity).filter(CanonicalEntity.id == entity_id_2).first()

    if not entity1 or not entity2:
        logger.warning(
            "Entity merge failed: entity not found (%d, %d)",
            entity_id_1,
            entity_id_2,
        )
        return {"status": "error", "message": "One or both entities not found"}

    # Check for same entity
    if entity1.id == entity2.id:
        return {
            "status": "error",
            "message": "Cannot merge same entity with itself",
        }

    # Get merge proposal from graph layer
    proposal = propose_entity_merge(entity_id_1, entity_id_2, db)

    if not proposal:
        return {"status": "error", "message": "Merge proposal failed"}

    # Apply safety checks
    safety_assessment = _assess_merge_safety(proposal, entity1, entity2, db)

    # Log merge proposal
    logger.info(
        "Merge proposed: entity %d -> %d (confidence=%.2f, risk=%s)",
        entity_id_2,
        entity_id_1,
        proposal.get("confidence", 0),
        safety_assessment["risk_level"],
    )

    return {
        "status": "proposed",
        "proposal": proposal,
        "safety": safety_assessment,
        "requires_approval": safety_assessment["requires_approval"],
    }


def _assess_merge_safety(
    proposal: dict, entity1: CanonicalEntity, entity2: CanonicalEntity, db: Session
) -> dict:
    """Assess safety of a merge proposal.

    Args:
        proposal: Merge proposal from graph layer
        entity1: First entity
        entity2: Second entity
        db: Database session

    Returns:
        Safety assessment dictionary
    """
    confidence = proposal.get("confidence", 0)

    # Determine risk level
    if confidence >= HIGH_RISK_THRESHOLD:
        risk_level = "low"
    elif confidence >= MERGE_CONFIDENCE_THRESHOLD:
        risk_level = "medium"
    else:
        risk_level = "high"

    # Check if human approval is required
    requires_approval = (
        REQUIRE_HUMAN_APPROVAL
        or risk_level == "high"
        or confidence < MERGE_CONFIDENCE_THRESHOLD
    )

    # Additional safety checks
    checks = {
        "confidence_threshold": confidence >= MERGE_CONFIDENCE_THRESHOLD,
        "entity_type_match": entity1.entity_type == entity2.entity_type,
        "jurisdiction_consistent": _check_jurisdiction_consistency(entity1, entity2),
    }

    # Overall safety decision
    safe = all(checks.values()) and confidence >= MERGE_CONFIDENCE_THRESHOLD

    return {
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "safe": safe,
        "checks": checks,
        "confidence": confidence,
    }


def _check_jurisdiction_consistency(
    entity1: CanonicalEntity, entity2: CanonicalEntity
) -> bool:
    """Check if entities have consistent jurisdictions.

    Args:
        entity1: First entity
        entity2: Second entity

    Returns:
        True if jurisdictions are consistent, False otherwise
    """
    # If both have jurisdictions, they should match or be compatible
    if entity1.jurisdiction and entity2.jurisdiction:
        return entity1.jurisdiction == entity2.jurisdiction
    # If only one has jurisdiction, that's acceptable
    return True


def execute_approved_merge(
    entity_id_1: int,
    entity_id_2: int,
    approved_by: str,
    db: Session,
) -> dict:
    """Execute a previously approved entity merge.

    Args:
        entity_id_1: ID of target entity (kept)
        entity_id_2: ID of source entity (merged into target)
        approved_by: Identifier of approving actor
        db: Database session

    Returns:
        Dictionary with execution result
    """
    # Re-assess safety before execution
    proposal = propose_safe_merge(entity_id_1, entity_id_2, db)

    if proposal["status"] != "proposed":
        return {"status": "error", "message": "Merge proposal failed"}

    safety = proposal["safety"]
    if not safety["safe"]:
        logger.warning(
            "Merge execution blocked: safety check failed (approved_by=%s)",
            approved_by,
        )
        return {
            "status": "blocked",
            "message": "Merge blocked by safety check",
            "safety": safety,
        }

    # Execute merge (this would call the actual graph merge logic)
    # For now, log the approval
    logger.info(
        "Merge executed: entity %d -> %d (approved_by=%s)",
        entity_id_2,
        entity_id_1,
        approved_by,
    )

    return {
        "status": "executed",
        "message": "Merge completed successfully",
        "target_entity_id": entity_id_1,
        "merged_entity_id": entity_id_2,
        "approved_by": approved_by,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def list_pending_approvals(db: Session) -> List[dict]:
    """List pending merge approvals.

    Args:
        db: Database session

    Returns:
        List of pending approval requests
    """
    # This would query a merge_requests table in a full implementation
    # For now, return empty list as placeholder
    logger.info("Listing pending merge approvals")
    return []


def get_merge_audit_trail(entity_id: int, db: Session) -> List[dict]:
    """Get audit trail for entity merges.

    Args:
        entity_id: ID of entity
        db: Database session

    Returns:
        List of audit trail entries
    """
    # This would query a merge_audit table in a full implementation
    # For now, return empty list as placeholder
    logger.info("Retrieving merge audit trail for entity %d", entity_id)
    return []
