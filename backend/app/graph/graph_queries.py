"""Authoritative graph query engine.

Replaces ``services/graph_queries.py`` as the canonical layer for reading
and writing edges. The service module will be kept as a thin shim that
imports from here.

All methods are read-only except ``write_edge``.  No LLM calls.

Typical usage::

    engine = GraphQueryEngine(db)
    edges  = engine.get_entity_edges("judge", judge_id, predicate="presided_over")
    paths  = engine.find_paths("judge", j_id, "case", c_id, max_depth=2)
    new_e  = engine.write_edge(
        subject_type="judge", subject_id=1,
        predicate="presided_over",
        object_type="case",  object_id=99,
        valid_from=datetime.now(timezone.utc),
        created_by="ingestion",
    )
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.graph.edge_models import EdgeKey, EdgeRecord
from app.graph.graph_models import GraphNode, GraphPath
from app.graph.confidence import propagate_confidence

_DEFAULT_LIMIT = 200


def _row_to_edge_record(row: Any) -> EdgeRecord:
    return EdgeRecord(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        predicate=row.predicate,
        object_type=row.object_type,
        object_id=row.object_id,
        evidence_refs=row.evidence_refs,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        status=row.status,
        created_by=row.created_by,
    )


class GraphQueryEngine:
    """Low-level graph query and write operations against EntityGraphEdge."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def get_entity_edges(
        self,
        entity_type: str,
        entity_id: int,
        *,
        as_subject: bool = True,
        as_object: bool = True,
        predicate: str | None = None,
        status: str = "active",
        limit: int = _DEFAULT_LIMIT,
    ) -> list[EdgeRecord]:
        """Return edges where the entity appears as subject and/or object.

        Args:
            entity_type: e.g. ``"judge"``, ``"case"``
            entity_id:   Primary key of the entity.
            as_subject:  Include edges where entity is the subject.
            as_object:   Include edges where entity is the object.
            predicate:   Optional filter on edge predicate.
            status:      Edge status filter (default ``"active"``).
            limit:       Maximum rows returned.

        Returns:
            List of EdgeRecord ordered by valid_from desc, id desc.
        """
        from app.models.entities import EntityGraphEdge

        conditions = []
        if as_subject:
            cond = (EntityGraphEdge.subject_type == entity_type) & (
                EntityGraphEdge.subject_id == entity_id
            )
            conditions.append(cond)
        if as_object:
            cond = (EntityGraphEdge.object_type == entity_type) & (
                EntityGraphEdge.object_id == entity_id
            )
            conditions.append(cond)

        if not conditions:
            return []

        q = self.db.query(EntityGraphEdge).filter(or_(*conditions))

        if status:
            q = q.filter(EntityGraphEdge.status == status)
        if predicate:
            q = q.filter(EntityGraphEdge.predicate == predicate)

        q = q.order_by(
            EntityGraphEdge.valid_from.desc(),
            EntityGraphEdge.id.desc(),
        ).limit(limit)

        return [_row_to_edge_record(r) for r in q.all()]

    def get_edge_by_key(self, key: EdgeKey) -> EdgeRecord | None:
        """Look up a single edge by its logical key (S-P-O triple).

        Returns the most-recently created edge matching the key, or None.
        """
        from app.models.entities import EntityGraphEdge

        row = (
            self.db.query(EntityGraphEdge)
            .filter(
                EntityGraphEdge.subject_type == key.subject_type,
                EntityGraphEdge.subject_id == key.subject_id,
                EntityGraphEdge.predicate == key.predicate,
                EntityGraphEdge.object_type == key.object_type,
                EntityGraphEdge.object_id == key.object_id,
            )
            .order_by(EntityGraphEdge.valid_from.desc())
            .first()
        )
        return _row_to_edge_record(row) if row is not None else None

    def get_neighborhood(
        self,
        entity_type: str,
        entity_id: int,
        depth: int = 1,
        status: str = "active",
    ) -> list[EdgeRecord]:
        """BFS-expand edges up to *depth* hops from the entity.

        depth=1 returns direct edges; depth=2 includes edges of those
        neighbours, etc.  Silently caps depth at 3.

        Args:
            entity_type: Starting entity type.
            entity_id:   Starting entity primary key.
            depth:       Expansion depth (1-3).
            status:      Edge status filter.

        Returns:
            Deduplicated list of EdgeRecord (order not guaranteed).
        """
        depth = min(max(depth, 1), 3)
        visited: set[tuple[str, int]] = set()
        frontier: deque[tuple[str, int]] = deque()
        frontier.append((entity_type, entity_id))
        collected: dict[int, EdgeRecord] = {}

        for _ in range(depth):
            next_frontier: deque[tuple[str, int]] = deque()
            while frontier:
                e_type, e_id = frontier.popleft()
                if (e_type, e_id) in visited:
                    continue
                visited.add((e_type, e_id))
                edges = self.get_entity_edges(e_type, e_id, status=status, limit=100)
                for edge in edges:
                    if edge.id not in collected:
                        collected[edge.id] = edge
                    # Queue neighbours
                    nbr_type = (
                        edge.object_type
                        if edge.subject_id == e_id
                        else edge.subject_type
                    )
                    nbr_id = (
                        edge.object_id if edge.subject_id == e_id else edge.subject_id
                    )
                    if (nbr_type, nbr_id) not in visited:
                        next_frontier.append((nbr_type, nbr_id))
            frontier = next_frontier

        return list(collected.values())

    def find_paths(
        self,
        from_type: str,
        from_id: int,
        to_type: str,
        to_id: int,
        max_depth: int = 3,
        status: str = "active",
    ) -> list[GraphPath]:
        """BFS path-finding between two entities.

        Returns up to 10 shortest paths.  Each path is a GraphPath with
        confidence propagated along the edge chain.  Returns early if no
        path exists within max_depth hops.

        Args:
            from_type:  Starting entity type.
            from_id:    Starting entity primary key.
            to_type:    Target entity type.
            to_id:      Target entity primary key.
            max_depth:  Maximum traversal depth (capped at 5).
            status:     Edge status filter.

        Returns:
            List of GraphPath (may be empty).
        """
        max_depth = min(max_depth, 5)
        target = (to_type, to_id)

        # BFS: state = (current_type, current_id, path_edges, path_confidence)
        queue: deque[tuple[str, int, list[EdgeRecord], float]] = deque()
        queue.append((from_type, from_id, [], 1.0))
        visited_at_depth: dict[tuple[str, int], int] = {}
        results: list[GraphPath] = []

        while queue and len(results) < 10:
            cur_type, cur_id, path_edges, path_conf = queue.popleft()
            depth = len(path_edges)

            if depth >= max_depth:
                continue

            key = (cur_type, cur_id)
            if visited_at_depth.get(key, 999) <= depth:
                continue
            visited_at_depth[key] = depth

            edges = self.get_entity_edges(cur_type, cur_id, status=status, limit=100)
            for edge in edges:
                # Determine the neighbour endpoint
                if edge.subject_type == cur_type and edge.subject_id == cur_id:
                    nbr_type, nbr_id = edge.object_type, edge.object_id
                else:
                    nbr_type, nbr_id = edge.subject_type, edge.subject_id

                new_conf = propagate_confidence(path_conf, 0.9)
                new_edges = path_edges + [edge]

                if (nbr_type, nbr_id) == target:
                    # Build GraphPath
                    start_node = GraphNode(
                        entity_type=from_type,
                        entity_id=from_id,
                        canonical_entity_id=None,
                        display_name=f"{from_type}:{from_id}",
                        confidence=1.0,
                    )
                    end_node = GraphNode(
                        entity_type=to_type,
                        entity_id=to_id,
                        canonical_entity_id=None,
                        display_name=f"{to_type}:{to_id}",
                        confidence=new_conf,
                    )
                    results.append(
                        GraphPath(
                            nodes=[start_node, end_node],
                            edges=new_edges,
                            total_confidence=new_conf,
                        )
                    )
                else:
                    queue.append((nbr_type, nbr_id, new_edges, new_conf))

        return results

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def write_edge(
        self,
        *,
        subject_type: str,
        subject_id: int,
        predicate: str,
        object_type: str,
        object_id: int,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        evidence_refs: dict | None = None,
        source_snapshot_id: int | None = None,
        created_by: str = "system",
        status: str = "active",
    ) -> EdgeRecord:
        """Upsert an edge into the EntityGraphEdge table.

        If an identical S-P-O + valid_from combination already exists,
        returns the existing EdgeRecord unchanged.

        Args:
            subject_type:       e.g. ``"judge"``
            subject_id:         Subject PK.
            predicate:          Edge predicate string.
            object_type:        e.g. ``"case"``
            object_id:          Object PK.
            valid_from:         Defaults to now (UTC).
            valid_until:        Defaults to None (open-ended).
            evidence_refs:      Optional JSON-serialisable dict.
            source_snapshot_id: FK into source snapshots (optional).
            created_by:         Audit identifier.
            status:             Edge status (default ``"active"``).

        Returns:
            EdgeRecord representing the new or existing edge.
        """
        from app.models.entities import EntityGraphEdge

        if valid_from is None:
            valid_from = datetime.now(timezone.utc)

        # Check for existing edge with same natural key
        existing = (
            self.db.query(EntityGraphEdge)
            .filter(
                EntityGraphEdge.subject_type == subject_type,
                EntityGraphEdge.subject_id == subject_id,
                EntityGraphEdge.predicate == predicate,
                EntityGraphEdge.object_type == object_type,
                EntityGraphEdge.object_id == object_id,
                EntityGraphEdge.valid_from == valid_from,
            )
            .first()
        )
        if existing is not None:
            return _row_to_edge_record(existing)

        row = EntityGraphEdge(
            subject_type=subject_type,
            subject_id=subject_id,
            predicate=predicate,
            object_type=object_type,
            object_id=object_id,
            valid_from=valid_from,
            valid_until=valid_until,
            evidence_refs=evidence_refs or {},
            source_snapshot_id=source_snapshot_id,
            created_by=created_by,
            status=status,
        )
        try:
            self.db.add(row)
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            # Someone inserted between our check and our write — re-fetch
            existing = (
                self.db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == subject_type,
                    EntityGraphEdge.subject_id == subject_id,
                    EntityGraphEdge.predicate == predicate,
                    EntityGraphEdge.object_type == object_type,
                    EntityGraphEdge.object_id == object_id,
                    EntityGraphEdge.valid_from == valid_from,
                )
                .first()
            )
            if existing is None:
                raise
            return _row_to_edge_record(existing)

        return _row_to_edge_record(row)
