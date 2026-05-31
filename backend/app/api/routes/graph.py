"""Graph API endpoints for entity relationships and timeline queries.

Provides REST endpoints for:
- Entity relationship queries (edges)
- Timeline reconstruction (court events)
- Path finding between entities
- Graph edge creation (admin only)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.admin import (
    log_mutation,
    require_admin_token,
)
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.security.import_authority import require_source_admin_actor
from app.services.graph_queries import GraphQueryService

router = APIRouter(prefix="/api/graph", tags=["graph"])


class EdgeCreateRequest(BaseModel):
    """Request to create a new graph edge."""

    subject_type: str
    subject_id: int
    predicate: str
    object_type: str
    object_id: int
    evidence_refs: dict[str, Any] | None = None
    source_snapshot_id: int | None = None
    valid_from: datetime | None = None


class EdgeResponse(BaseModel):
    """Graph edge response."""

    id: int
    subject_type: str
    subject_id: int
    predicate: str
    object_type: str
    object_id: int
    evidence_refs: dict | None
    valid_from: datetime
    valid_until: datetime | None
    status: str
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class TimelineEventResponse(BaseModel):
    """Timeline event response."""

    event_id: int
    event_type: str
    event_date: datetime
    description: str | None
    outcome: str | None
    entities: list[dict[str, Any]]
    documents: list[dict] | None


class PathResponse(BaseModel):
    """Path finding response."""

    paths: list[list[EdgeResponse]]
    path_count: int


class RelatedEntityResponse(BaseModel):
    """Related entity response."""

    edge_id: int
    predicate: str
    direction: str  # "incoming" or "outgoing"
    related_entity_type: str
    related_entity_id: int
    evidence_refs: dict | None
    valid_from: datetime
    valid_until: datetime | None


@router.get("/entity/{entity_type}/{entity_id}/edges")
def get_entity_edges(
    entity_type: str,
    entity_id: int,
    as_subject: bool = Query(True, description="Include edges where entity is subject"),
    as_object: bool = Query(True, description="Include edges where entity is object"),
    predicate: str | None = Query(None, description="Filter by predicate"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get all graph edges connected to an entity."""
    service = GraphQueryService(db)
    edges = service.get_entity_edges(
        entity_type=entity_type,
        entity_id=entity_id,
        as_subject=as_subject,
        as_object=as_object,
        predicate=predicate,
        limit=limit,
    )

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total_edges": len(edges),
        "edges": [
            {
                "id": e.id,
                "subject_type": e.subject_type,
                "subject_id": e.subject_id,
                "predicate": e.predicate,
                "object_type": e.object_type,
                "object_id": e.object_id,
                "evidence_refs": e.evidence_refs,
                "valid_from": e.valid_from,
                "valid_until": e.valid_until,
                "status": e.status,
            }
            for e in edges
        ],
    }


@router.get("/entity/{entity_type}/{entity_id}/related")
def get_related_entities(
    entity_type: str,
    entity_id: int,
    predicate: str | None = Query(None, description="Filter by relationship type"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get entities directly related to the given entity."""
    service = GraphQueryService(db)
    related = service.get_related_entities(
        entity_type=entity_type,
        entity_id=entity_id,
        predicate=predicate,
        limit=limit,
    )

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total_related": len(related),
        "related_entities": related,
    }


@router.get("/case/{case_id}/timeline")
def get_case_timeline(
    case_id: int,
    include_documents: bool = Query(True, description="Include document references"),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> dict[str, Any]:
    """Get chronological timeline for a case."""
    service = GraphQueryService(db)
    timeline = service.get_case_timeline(
        case_id=case_id,
        include_documents=include_documents,
    )

    return {
        "case_id": case_id,
        "total_events": len(timeline),
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "event_date": e.event_date,
                "description": e.description,
                "outcome": e.outcome,
                "entities": e.entities,
                "documents": e.documents,
            }
            for e in timeline
        ],
    }


@router.get("/path")
def find_path(
    from_type: str = Query(..., description="Source entity type"),
    from_id: int = Query(..., description="Source entity ID"),
    to_type: str = Query(..., description="Target entity type"),
    to_id: int = Query(..., description="Target entity ID"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum path length"),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> PathResponse:
    """Find paths between two entities."""
    service = GraphQueryService(db)
    paths = service.find_path(
        from_type=from_type,
        from_id=from_id,
        to_type=to_type,
        to_id=to_id,
        max_depth=max_depth,
    )

    if not paths:
        return PathResponse(paths=[], path_count=0)

    return PathResponse(
        paths=[
            [
                EdgeResponse(
                    id=e.id,
                    subject_type=e.subject_type,
                    subject_id=e.subject_id,
                    predicate=e.predicate,
                    object_type=e.object_type,
                    object_id=e.object_id,
                    evidence_refs=e.evidence_refs,
                    valid_from=e.valid_from,
                    valid_until=e.valid_until,
                    status=e.status,
                    created_by="system",  # Simplified
                )
                for e in path
            ]
            for path in paths
        ],
        path_count=len(paths),
    )


@router.post("/edges", response_model=EdgeResponse)
def create_edge(
    request: EdgeCreateRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> EdgeResponse:
    """Create a new graph edge (source_admin only)."""
    service = GraphQueryService(db)

    try:
        edge = service.create_edge(
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            predicate=request.predicate,
            object_type=request.object_type,
            object_id=request.object_id,
            evidence_refs=request.evidence_refs,
            source_snapshot_id=request.source_snapshot_id,
            created_by=actor.actor_id,
            valid_from=request.valid_from,
            auto_commit=False,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    try:
        log_mutation(
            action="graph.edge.create",
            entity_type="entity_graph_edge",
            entity_id=str(edge.id),
            payload={"predicate": request.predicate},
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Audit logging failed; mutation aborted",
        )

    return EdgeResponse(
        id=edge.id,
        subject_type=edge.subject_type,
        subject_id=edge.subject_id,
        predicate=edge.predicate,
        object_type=edge.object_type,
        object_id=edge.object_id,
        evidence_refs=edge.evidence_refs,
        valid_from=edge.valid_from,
        valid_until=edge.valid_until,
        status=edge.status,
        created_by=edge.created_by,
    )
