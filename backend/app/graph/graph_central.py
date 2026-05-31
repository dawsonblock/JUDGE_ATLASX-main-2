"""Central graph layer for entity resolution and claim mapping.

Implements graph-based entity resolution, claim-to-entity mapping,
and entity state rebuilds.
"""

import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.entities import (
    CanonicalEntity,
    MemoryClaim,
    MemoryEntityState,
    EntityGraphEdge,
)
from app.memory import hash_utils

logger = logging.getLogger(__name__)


def resolve_entity_from_claim(claim: MemoryClaim, db: Session) -> CanonicalEntity:
    """Resolve the canonical entity for a claim using graph layer.

    Args:
        claim: The claim to resolve entity for
        db: Database session

    Returns:
        CanonicalEntity resolved from claim
    """
    # If claim already has entity_id, return that entity
    if claim.entity_id:
        entity = (
            db.query(CanonicalEntity)
            .filter(CanonicalEntity.id == claim.entity_id)
            .first()
        )
        if entity:
            return entity

    # Fallback: create new entity (placeholder)
    logger.warning("Could not resolve entity for claim %d", claim.id)
    raise ValueError(f"Could not resolve entity for claim {claim.id}")


def map_claims_to_entities(db: Session) -> int:
    """Map all claims to entities using graph layer.

    Args:
        db: Database session

    Returns:
        Number of claims mapped
    """
    claims = db.query(MemoryClaim).filter(MemoryClaim.is_active == True).all()
    mapped_count = 0

    for claim in claims:
        try:
            entity = resolve_entity_from_claim(claim, db)
            if entity and entity.id != claim.entity_id:
                claim.entity_id = entity.id
                mapped_count += 1
        except ValueError:
            continue

    db.commit()
    logger.info("Mapped %d claims to entities using graph layer", mapped_count)
    return mapped_count


def rebuild_entity_state(entity_id: int, db: Session) -> MemoryEntityState:
    """Rebuild entity state from all active claims using graph layer.

    Args:
        entity_id: ID of entity to rebuild
        db: Database session

    Returns:
        Updated MemoryEntityState
    """
    entity = (
        db.query(CanonicalEntity).filter(CanonicalEntity.id == entity_id).first()
    )
    if not entity:
        raise ValueError(f"Entity {entity_id} not found")

    # Get all active claims for this entity
    claims = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active == True,
            MemoryClaim.status == "active",
        )
        .all()
    )

    # Build state summary from claims
    state_data = _build_state_summary(entity, claims)

    # Calculate state checksum
    state_checksum = hash_utils.stable_json_hash(state_data)

    # Update or create entity state
    entity_state = (
        db.query(MemoryEntityState)
        .filter(MemoryEntityState.entity_id == entity_id)
        .first()
    )

    if entity_state:
        entity_state.state_checksum = state_checksum
        entity_state.display_name = state_data.get("display_name")
        entity_state.aliases = state_data.get("aliases", [])
        entity_state.roles = state_data.get("roles", [])
        entity_state.jurisdictions = state_data.get("jurisdictions", [])
        entity_state.biography_summary = state_data.get("biography_summary")
        entity_state.rebuilt_at = state_data.get("rebuilt_at")
    else:
        entity_state = MemoryEntityState(
            entity_id=entity_id,
            state_checksum=state_checksum,
            display_name=state_data.get("display_name"),
            aliases=state_data.get("aliases", []),
            roles=state_data.get("roles", []),
            jurisdictions=state_data.get("jurisdictions", []),
            biography_summary=state_data.get("biography_summary"),
        )
        db.add(entity_state)

    db.commit()
    db.refresh(entity_state)

    logger.info("Rebuilt entity state for entity %d (checksum=%s)", entity_id, state_checksum)
    return entity_state


def _build_state_summary(
    entity: CanonicalEntity, claims: List[MemoryClaim]
) -> Dict[str, any]:
    """Build state summary from entity and claims.

    Args:
        entity: Canonical entity
        claims: List of active claims

    Returns:
        State summary dictionary
    """
    from datetime import datetime, timezone

    summary = {
        "display_name": entity.canonical_name,
        "aliases": [],
        "roles": [],
        "jurisdictions": [],
        "biography_summary": None,
        "rebuilt_at": datetime.now(timezone.utc).isoformat(),
    }

    # Extract information from claims
    for claim in claims:
        if claim.claim_type == "alias":
            if claim.normalized_value and claim.normalized_value not in summary["aliases"]:
                summary["aliases"].append(claim.normalized_value)
        elif claim.claim_type == "role":
            if claim.normalized_value and claim.normalized_value not in summary["roles"]:
                summary["roles"].append(claim.normalized_value)
        elif claim.claim_type == "jurisdiction":
            if (
                claim.normalized_value
                and claim.normalized_value not in summary["jurisdictions"]
            ):
                summary["jurisdictions"].append(claim.normalized_value)
        elif claim.claim_type == "biography":
            if claim.normalized_value:
                summary["biography_summary"] = claim.normalized_value

    return summary


def batch_rebuild_entity_states(db: Session) -> int:
    """Rebuild entity states for all entities.

    Args:
        db: Database session

    Returns:
        Number of entities rebuilt
    """
    entities = db.query(CanonicalEntity).all()
    rebuilt_count = 0

    for entity in entities:
        try:
            rebuild_entity_state(entity.id, db)
            rebuilt_count += 1
        except ValueError:
            logger.warning("Failed to rebuild state for entity %d", entity.id)

    logger.info("Rebuilt entity states for %d entities", rebuilt_count)
    return rebuilt_count


def get_entity_graph(entity_id: int, db: Session) -> Dict[str, any]:
    """Get graph representation of an entity and its connections.

    Args:
        entity_id: ID of entity
        db: Database session

    Returns:
        Graph representation dictionary
    """
    entity = (
        db.query(CanonicalEntity).filter(CanonicalEntity.id == entity_id).first()
    )
    if not entity:
        raise ValueError(f"Entity {entity_id} not found")

    # Get outgoing edges
    outgoing_edges = (
        db.query(EntityGraphEdge)
        .filter(EntityGraphEdge.subject_id == entity_id)
        .all()
    )

    # Get incoming edges
    incoming_edges = (
        db.query(EntityGraphEdge)
        .filter(EntityGraphEdge.object_id == entity_id)
        .all()
    )

    # Build graph representation
    graph = {
        "entity": {
            "id": entity.id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
        },
        "outgoing_edges": [
            {
                "id": edge.id,
                "predicate": edge.predicate,
                "object_type": edge.object_type,
                "object_id": edge.object_id,
                "evidence_refs": edge.evidence_refs,
                "valid_from": edge.valid_from,
            }
            for edge in outgoing_edges
        ],
        "incoming_edges": [
            {
                "id": edge.id,
                "predicate": edge.predicate,
                "subject_type": edge.subject_type,
                "subject_id": edge.subject_id,
                "evidence_refs": edge.evidence_refs,
                "valid_from": edge.valid_from,
            }
            for edge in incoming_edges
        ],
    }

    return graph
