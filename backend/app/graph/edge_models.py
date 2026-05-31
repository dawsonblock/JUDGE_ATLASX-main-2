"""Typed edge predicates, entity types, and edge dataclasses.

Provides the vocabulary of relationships stored in the entity_graph_edges
table together with immutable value objects used throughout the graph
package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EdgePredicate(str, Enum):
    """Known relationship predicates for the graph.

    Values match the ``predicate`` column in entity_graph_edges.
    """

    PRESIDED_OVER = "presided_over"
    CHARGED_IN = "charged_in"
    LOCATED_AT = "located_at"
    APPEALED_TO = "appealed_to"
    REPRESENTS = "represents"
    WITNESSED = "witnessed"
    LINKED_TO = "linked_to"
    MERGED_INTO = "merged_into"
    ASSIGNED_TO = "assigned_to"
    SENTENCED_BY = "sentenced_by"
    EMPLOYED_BY = "employed_by"
    OCCURRED_AT = "occurred_at"
    RELATED_TO = "related_to"


class EntityType(str, Enum):
    """Entity types that participate in graph edges."""

    JUDGE = "judge"
    CASE = "case"
    COURT = "court"
    DEFENDANT = "defendant"
    INCIDENT = "incident"
    CANONICAL_ENTITY = "canonical_entity"
    LOCATION = "location"
    SOURCE = "source"


@dataclass(frozen=True)
class EdgeKey:
    """Immutable identifier for a unique directed edge (ignores valid_from).

    Two edges with the same key but different ``valid_from`` are temporal
    versions of the same relationship.
    """

    subject_type: str
    subject_id: int
    predicate: str
    object_type: str
    object_id: int


@dataclass
class EdgeRecord:
    """Lightweight, serialisable representation of a graph edge.

    Mirrors the columns of entity_graph_edges without ORM overhead.
    """

    id: int
    subject_type: str
    subject_id: int
    predicate: str
    object_type: str
    object_id: int
    evidence_refs: dict | None
    valid_from: datetime
    valid_until: datetime | None
    status: str  # "active", "disputed", "retracted"
    created_by: str

    @property
    def key(self) -> EdgeKey:
        """Return the EdgeKey for this record."""
        return EdgeKey(
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            predicate=self.predicate,
            object_type=self.object_type,
            object_id=self.object_id,
        )

    def is_active_at(self, at: datetime) -> bool:
        """Return True if this edge is valid at the given point in time."""
        if self.status != "active":
            return False
        if self.valid_from > at:
            return False
        if self.valid_until is not None and self.valid_until <= at:
            return False
        return True
