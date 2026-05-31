"""Convert memory claims to graph entities and relationships (Phase 9).

This module provides functions to transform structured memory claims
into graph entities and relationships for the knowledge graph.

Key functions:
- claim_to_entity_node: Convert a claim to an entity node
- claim_to_relationship: Convert a claim to a relationship edge
- batch_claims_to_graph: Batch process claims for graph integration
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.entities import MemoryClaim, CanonicalEntity, EntityGraphEdge
from app.graph.graph_models import EntityNode, RelationshipEdge
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)


def claim_to_entity_node(claim: MemoryClaim, db: Session) -> EntityNode:
    """Convert a memory claim to a graph entity node.

    Args:
        claim: The memory claim to convert
        db: Database session

    Returns:
        EntityNode representation of the claim

    Raises:
        ValueError: If claim entity is not found
    """
    entity = db.query(CanonicalEntity).filter(
        CanonicalEntity.id == claim.entity_id
    ).first()

    if not entity:
        raise ValueError(f"Entity {claim.entity_id} not found for claim {claim.id}")

    # Build entity node properties from claim
    properties: Dict[str, Any] = {
        "claim_id": claim.id,
        "claim_key": claim.claim_key,
        "claim_uid": claim.claim_uid,
        "claim_type": claim.claim_type,
        "predicate": claim.predicate,
        "object_value": claim.object_value,
        "object_value_type": claim.object_value_type,
        "normalized_value": claim.normalized_value,
        "confidence": claim.confidence,
        "jurisdiction": claim.jurisdiction,
        "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
        "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
        "observed_at": claim.observed_at.isoformat() if claim.observed_at else None,
        "source_quality": claim.source_quality,
        "corroboration_count": claim.corroboration_count,
        "contradiction_count": claim.contradiction_count,
        "review_status": claim.review_status,
        "status": claim.status,
        "is_active": claim.is_active,
        # Phase 6 edge fields
        "claim_sensitivity": claim.claim_sensitivity,
        "elevated_review_status": claim.elevated_review_status,
        "elevated_reviewer_id": claim.elevated_reviewer_id,
        "elevated_reviewed_at": (
            claim.elevated_reviewed_at.isoformat()
            if claim.elevated_reviewed_at
            else None
        ),
        "derived_from_ai": claim.derived_from_ai,
        "extraction_model": claim.extraction_model,
        "last_seen_at": claim.last_seen_at.isoformat() if claim.last_seen_at else None,
    }

    # Create entity node
    node = EntityNode(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        properties=properties,
    )

    return node


def claim_to_relationship(claim: MemoryClaim, db: Session) -> Optional[RelationshipEdge]:
    """Convert a memory claim to a graph relationship edge.

    Args:
        claim: The memory claim to convert
        db: Database session

    Returns:
        RelationshipEdge representation of the claim, or None if
        not a relationship claim or edge should be hidden

    Raises:
        ValueError: If claim entity or object entity is not found
    """
    # Only convert claims with object_entity_id to relationships
    if not claim.object_entity_id:
        return None

    # Phase 6: Status-based edge visibility rules
    # Hide edges for disputed, rejected, or superseded claims
    if claim.status in ["disputed", "rejected", "superseded"]:
        logger.info(
            "Skipping edge for claim %s with status %s (status-based hiding)",
            claim.id, claim.status
        )
        return None

    # Phase 6: Contradiction-based edge hiding
    # Hide edges for claims with open critical contradictions
    if claim.contradiction_count and claim.contradiction_count > 0:
        from app.models.entities import MemoryContradiction

        open_critical = (
            db.query(MemoryContradiction)
            .filter(
                (MemoryContradiction.claim_a_id == claim.id)
                | (MemoryContradiction.claim_b_id == claim.id),
                MemoryContradiction.status == "open",
                MemoryContradiction.severity == "critical"
            )
            .first()
        )
        if open_critical:
            logger.info(
                "Skipping edge for claim %s with open critical "
                "contradiction (contradiction-based hiding)",
                claim.id
            )
            return None

    source_entity = db.query(CanonicalEntity).filter(
        CanonicalEntity.id == claim.entity_id
    ).first()

    target_entity = db.query(CanonicalEntity).filter(
        CanonicalEntity.id == claim.object_entity_id
    ).first()

    if not source_entity:
        raise ValueError(f"Source entity {claim.entity_id} not found for claim {claim.id}")

    if not target_entity:
        raise ValueError(f"Target entity {claim.object_entity_id} not found for claim {claim.id}")

    # Build relationship properties from claim
    properties: Dict[str, Any] = {
        "claim_id": claim.id,
        "claim_key": claim.claim_key,
        "claim_uid": claim.claim_uid,
        "claim_type": claim.claim_type,
        "predicate": claim.predicate,
        "object_value": claim.object_value,
        "object_value_type": claim.object_value_type,
        "normalized_value": claim.normalized_value,
        "confidence": claim.confidence,
        "jurisdiction": claim.jurisdiction,
        "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
        "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
        "observed_at": claim.observed_at.isoformat() if claim.observed_at else None,
        "source_quality": claim.source_quality,
        "corroboration_count": claim.corroboration_count,
        "contradiction_count": claim.contradiction_count,
        "review_status": claim.review_status,
        "status": claim.status,
        "is_active": claim.is_active,
        # Phase 6 edge fields
        "claim_sensitivity": claim.claim_sensitivity,
        "elevated_review_status": claim.elevated_review_status,
        "elevated_reviewer_id": claim.elevated_reviewer_id,
        "elevated_reviewed_at": (
            claim.elevated_reviewed_at.isoformat()
            if claim.elevated_reviewed_at
            else None
        ),
        "derived_from_ai": claim.derived_from_ai,
        "extraction_model": claim.extraction_model,
        "last_seen_at": claim.last_seen_at.isoformat() if claim.last_seen_at else None,
    }

    # Create relationship edge
    edge = RelationshipEdge(
        source_entity_id=source_entity.id,
        target_entity_id=target_entity.id,
        relationship_type=claim.predicate or claim.claim_type,
        properties=properties,
    )

    return edge


def batch_claims_to_graph(
    claims: List[MemoryClaim],
    db: Session,
    include_relationships: bool = True,
) -> Dict[str, Any]:
    """Batch process claims for graph integration.

    Args:
        claims: List of memory claims to process
        db: Database session
        include_relationships: Whether to also create relationship edges

    Returns:
        Dictionary with processing statistics:
        - entities_created: Number of entity nodes created
        - relationships_created: Number of relationship edges created
        - errors: List of error messages
    """
    stats: Dict[str, Any] = {
        "entities_created": 0,  # type: ignore[assignment]
        "relationships_created": 0,  # type: ignore[assignment]
        "errors": [],  # type: ignore[assignment]
    }

    for claim in claims:
        try:
            # Convert claim to entity node (validation)
            claim_to_entity_node(claim, db)
            stats["entities_created"] += 1

            # Optionally create relationship
            if include_relationships:
                edge = claim_to_relationship(claim, db)
                if edge:
                    stats["relationships_created"] += 1

        except ValueError as e:
            # Expected errors (missing entities, etc.)
            error_msg = f"Failed to process claim {claim.id}: {str(e)}"
            stats["errors"].append(error_msg)
            logger.warning(error_msg)
        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error processing claim {claim.id}: {str(e)}"
            stats["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True)

    return stats


def sync_claim_to_graph(claim: MemoryClaim, db: Session) -> bool:
    """Sync a single claim to the graph (create or update).

    Args:
        claim: The memory claim to sync
        db: Database session

    Returns:
        True if sync was successful, False otherwise
    """
    try:
        # Convert claim to entity node (validation only)
        claim_to_entity_node(claim, db)

        if claim.object_entity_id:
            # Keep graph edges in sync with claim visibility transitions.
            hidden_statuses = {"disputed", "rejected", "superseded"}
            sibling_edges = db.query(EntityGraphEdge).filter(
                EntityGraphEdge.subject_type == "canonical_entity",
                EntityGraphEdge.subject_id == claim.entity_id,
                EntityGraphEdge.object_type == "canonical_entity",
                EntityGraphEdge.object_id == claim.object_entity_id,
                EntityGraphEdge.status == "active",
            ).all()
            for sibling_edge in sibling_edges:
                evidence_refs = sibling_edge.evidence_refs or {}
                if not isinstance(evidence_refs, dict):
                    continue
                sibling_claim_id = evidence_refs.get("claim_id")
                if not sibling_claim_id:
                    continue
                sibling_claim = db.query(MemoryClaim).filter(
                    MemoryClaim.id == sibling_claim_id
                ).first()
                if sibling_claim and sibling_claim.status in hidden_statuses:
                    sibling_edge.status = "retracted"
                    sibling_edge.valid_until = func.now()
                    sibling_edge.updated_at = func.now()

        # Convert claim to relationship if applicable and persist to database
        edge = claim_to_relationship(claim, db)
        if edge:
            # Use merge for upsert to avoid race condition
            # Check if edge already exists
            existing_edge = db.query(EntityGraphEdge).filter(
                EntityGraphEdge.subject_type == "canonical_entity",
                EntityGraphEdge.subject_id == edge.source_entity_id,
                EntityGraphEdge.predicate == edge.relationship_type,
                EntityGraphEdge.object_type == "canonical_entity",
                EntityGraphEdge.object_id == edge.target_entity_id,
                EntityGraphEdge.status == "active"
            ).with_for_update().first()

            if existing_edge:
                # Update existing edge with new properties
                existing_edge.evidence_refs = edge.properties
                existing_edge.updated_at = func.now()
                logger.debug(f"Updated existing graph edge for claim {claim.id}")
            else:
                # Create new edge
                new_edge = EntityGraphEdge(
                    subject_type="canonical_entity",
                    subject_id=edge.source_entity_id,
                    predicate=edge.relationship_type,
                    object_type="canonical_entity",
                    object_id=edge.target_entity_id,
                    evidence_refs=edge.properties,
                    source_snapshot_id=(
                        claim.source_snapshot_id if hasattr(claim, "source_snapshot_id") else None
                    ),
                    valid_from=claim.valid_from if claim.valid_from else func.now(),
                    valid_until=claim.valid_to,
                    created_by="ingestion",
                    status="active"
                )
                db.add(new_edge)
                logger.debug(f"Created new graph edge for claim {claim.id}")

            db.commit()
            return True

        # If relationship edges are hidden by status, retract any existing active edges.
        if claim.object_entity_id and claim.status in ["disputed", "rejected", "superseded"]:
            remove_claim_from_graph(claim, db)
            return True

        # If no edge (e.g., claim doesn't have object_entity_id or is hidden), still return True
        return True
    except Exception as e:
        # Log error but don't raise
        db.rollback()
        logger.error(f"Error syncing claim {claim.id} to graph: {e}", exc_info=True)
        return False


def remove_claim_from_graph(claim: MemoryClaim, db: Session) -> bool:
    """Remove a claim from the graph by deactivating/hiding its edges.

    Args:
        claim: The memory claim to remove
        db: Database session

    Returns:
        True if removal was successful, False otherwise

    Note:
        This function deactivates edges rather than deleting them to preserve
        audit trail. Edges are marked with status="retracted" and valid_until set.
        Only deactivates edges where this claim is the subject (entity_id),
        not where it appears as an object (to avoid deactivating edges created by other claims).
    """
    try:
        # Find only active graph edges where this claim is the subject
        # We do NOT search by object_entity_id to avoid deactivating edges
        # that were created by other claims about this entity
        edges = db.query(EntityGraphEdge).filter(
            EntityGraphEdge.subject_type == "canonical_entity",
            EntityGraphEdge.subject_id == claim.entity_id,
            EntityGraphEdge.status == "active"
        ).all()

        # Deactivate all edges by setting status to "retracted" and valid_until
        for edge in edges:
            edge.status = "retracted"
            edge.valid_until = func.now()
            edge.updated_at = func.now()
            logger.debug(f"Deactivated graph edge {edge.id} for claim {claim.id}")

        db.commit()
        logger.info(f"Deactivated {len(edges)} graph edges for claim {claim.id}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing claim {claim.id} from graph: {e}", exc_info=True)
        return False
