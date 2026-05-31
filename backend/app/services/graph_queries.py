"""Graph query service for entity relationship traversal.

Provides path finding, neighborhood queries, and timeline reconstruction
using the EntityGraphEdge S-P-O triple store.

NOTE: Authoritative graph implementation now lives in app.graph.
This service re-exports the canonical classes below and retains its own
legacy helpers for backward compatibility.
"""

from __future__ import annotations

# Shim: expose graph-package classes through this module
from app.graph.graph_queries import GraphQueryEngine  # noqa: F401
from app.graph.edge_models import EdgeRecord  # noqa: F401

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.entities import CourtEvent, EntityGraphEdge


@dataclass
class GraphEdge:
    """Simplified edge representation for API responses."""

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


@dataclass
class TimelineEvent:
    """Event for timeline reconstruction."""

    event_id: int
    event_type: str
    event_date: datetime
    description: str | None
    outcome: str | None
    entities: list[dict[str, Any]]  # [{"type": "judge", "id": 1, "name": "..."}]
    documents: list[dict] | None


class GraphQueryService:
    """Service for executing graph queries and traversals."""

    def __init__(self, db: Session):
        self.db = db

    def get_entity_edges(
        self,
        entity_type: str,
        entity_id: int,
        as_subject: bool = True,
        as_object: bool = True,
        predicate: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[GraphEdge]:
        """Get all edges connected to an entity.

        Args:
            entity_type: Type of the entity (judge, case, etc.)
            entity_id: ID of the entity
            as_subject: Include edges where entity is the subject
            as_object: Include edges where entity is the object
            predicate: Filter by specific predicate (optional)
            status: Edge status filter
            limit: Maximum number of edges to return

        Returns:
            List of GraphEdge objects
        """
        query = self.db.query(EntityGraphEdge).filter(EntityGraphEdge.status == status)

        # Build the filter for subject or object
        if as_subject and as_object:
            query = query.filter(
                (
                    (EntityGraphEdge.subject_type == entity_type)
                    & (EntityGraphEdge.subject_id == entity_id)
                )
                | (
                    (EntityGraphEdge.object_type == entity_type)
                    & (EntityGraphEdge.object_id == entity_id)
                )
            )
        elif as_subject:
            query = query.filter(
                (EntityGraphEdge.subject_type == entity_type)
                & (EntityGraphEdge.subject_id == entity_id)
            )
        elif as_object:
            query = query.filter(
                (EntityGraphEdge.object_type == entity_type)
                & (EntityGraphEdge.object_id == entity_id)
            )
        else:
            return []

        if predicate:
            query = query.filter(EntityGraphEdge.predicate == predicate)

        edges = query.order_by(desc(EntityGraphEdge.created_at)).limit(limit).all()

        return [
            GraphEdge(
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
            )
            for e in edges
        ]

    def get_case_timeline(
        self,
        case_id: int,
        include_documents: bool = True,
    ) -> list[TimelineEvent]:
        """Get chronological timeline for a case.

        Args:
            case_id: ID of the case
            include_documents: Whether to include document references

        Returns:
            List of TimelineEvent objects sorted by date
        """
        events = (
            self.db.query(CourtEvent)
            .filter(CourtEvent.case_id == case_id)
            .order_by(CourtEvent.event_date)
            .all()
        )

        timeline: list[TimelineEvent] = []
        for event in events:
            # Build entity list
            entities = []
            if event.judge_id and event.judge:
                entities.append(
                    {
                        "type": "judge",
                        "id": event.judge_id,
                        "name": event.judge.canonical_name,
                    }
                )
            if event.court_id and event.court:
                entities.append(
                    {
                        "type": "court",
                        "id": event.court_id,
                        "name": event.court.canonical_name,
                    }
                )

            timeline.append(
                TimelineEvent(
                    event_id=event.id,
                    event_type=event.event_type,
                    event_date=event.event_date,
                    description=event.description,
                    outcome=event.outcome,
                    entities=entities,
                    documents=event.documents if include_documents else None,
                )
            )

        return timeline

    def find_path(
        self,
        from_type: str,
        from_id: int,
        to_type: str,
        to_id: int,
        max_depth: int = 3,
    ) -> list[list[GraphEdge]] | None:
        """Find paths between two entities using BFS.

        Args:
            from_type: Starting entity type
            from_id: Starting entity ID
            to_type: Target entity type
            to_id: Target entity ID
            max_depth: Maximum path length to search

        Returns:
            List of paths (each path is a list of GraphEdges), or None if no path found
        """
        # BFS implementation
        from collections import deque

        # Queue holds: (current_entity_type, current_entity_id, path_so_far)
        queue: deque[tuple[str, int, list[EntityGraphEdge]]] = deque(
            [(from_type, from_id, [])]
        )
        visited: set[tuple[str, int]] = {(from_type, from_id)}
        found_paths: list[list[GraphEdge]] = []

        while queue and len(found_paths) < 5:  # Limit to 5 paths
            current_type, current_id, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            # Get edges from current entity
            edges = (
                self.db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.status == "active",
                    (
                        (EntityGraphEdge.subject_type == current_type)
                        & (EntityGraphEdge.subject_id == current_id)
                    )
                    | (
                        (EntityGraphEdge.object_type == current_type)
                        & (EntityGraphEdge.object_id == current_id)
                    ),
                )
                .all()
            )

            for edge in edges:
                # Determine next entity
                if edge.subject_type == current_type and edge.subject_id == current_id:
                    next_type = edge.object_type
                    next_id = edge.object_id
                else:
                    next_type = edge.subject_type
                    next_id = edge.subject_id

                # Check if we reached the target
                if next_type == to_type and next_id == to_id:
                    # Found a path
                    full_path = path + [edge]
                    found_paths.append(
                        [
                            GraphEdge(
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
                            )
                            for e in full_path
                        ]
                    )
                elif (next_type, next_id) not in visited:
                    visited.add((next_type, next_id))
                    queue.append((next_type, next_id, path + [edge]))

        return found_paths if found_paths else None

    def get_related_entities(
        self,
        entity_type: str,
        entity_id: int,
        predicate: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get entities directly related to the given entity.

        Args:
            entity_type: Type of the source entity
            entity_id: ID of the source entity
            predicate: Optional predicate filter
            limit: Maximum results

        Returns:
            List of related entities with relationship info
        """
        query = self.db.query(EntityGraphEdge).filter(
            EntityGraphEdge.status == "active"
        )

        # Match as either subject or object
        query = query.filter(
            (
                (EntityGraphEdge.subject_type == entity_type)
                & (EntityGraphEdge.subject_id == entity_id)
            )
            | (
                (EntityGraphEdge.object_type == entity_type)
                & (EntityGraphEdge.object_id == entity_id)
            )
        )

        if predicate:
            query = query.filter(EntityGraphEdge.predicate == predicate)

        edges = query.limit(limit).all()

        results = []
        for edge in edges:
            # Determine direction and related entity
            if edge.subject_type == entity_type and edge.subject_id == entity_id:
                related_type = edge.object_type
                related_id = edge.object_id
                direction = "outgoing"
            else:
                related_type = edge.subject_type
                related_id = edge.subject_id
                direction = "incoming"

            results.append(
                {
                    "edge_id": edge.id,
                    "predicate": edge.predicate,
                    "direction": direction,
                    "related_entity_type": related_type,
                    "related_entity_id": related_id,
                    "evidence_refs": edge.evidence_refs,
                    "valid_from": edge.valid_from,
                    "valid_until": edge.valid_until,
                }
            )

        return results

    def create_edge(
        self,
        subject_type: str,
        subject_id: int,
        predicate: str,
        object_type: str,
        object_id: int,
        evidence_refs: dict | None = None,
        source_snapshot_id: int | None = None,
        created_by: str = "api",
        valid_from: datetime | None = None,
        auto_commit: bool = True,
    ) -> EntityGraphEdge:
        """Create a new graph edge.

        Args:
            subject_type: Subject entity type
            subject_id: Subject entity ID
            predicate: Relationship type
            object_type: Object entity type
            object_id: Object entity ID
            evidence_refs: Evidence references
            source_snapshot_id: Optional snapshot ID
            created_by: Creator identifier
            valid_from: Validity start date (default: now)

        Returns:
            Created EntityGraphEdge
        """
        edge = EntityGraphEdge(
            subject_type=subject_type,
            subject_id=subject_id,
            predicate=predicate,
            object_type=object_type,
            object_id=object_id,
            evidence_refs=evidence_refs,
            source_snapshot_id=source_snapshot_id,
            created_by=created_by,
            status="active",
            valid_from=valid_from or datetime.now(timezone.utc),
        )
        self.db.add(edge)
        if auto_commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(edge)
        return edge
