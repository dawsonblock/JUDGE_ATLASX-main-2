"""Graph node and path dataclasses.

Provides the value objects used to represent entities and traversal
results without coupling callers to SQLAlchemy ORM models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        from app.graph.edge_models import EdgeRecord
    except ImportError:
        EdgeRecord = None  # type: ignore


@dataclass
class GraphNode:
    """A node in the entity graph.

    Corresponds to a real-world entity (judge, case, etc.) resolved to
    its canonical identity.  ``confidence`` reflects how certain we are
    about the canonical mapping.
    """

    entity_type: str
    entity_id: int
    canonical_entity_id: int | None
    display_name: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.entity_type, self.entity_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GraphNode):
            return NotImplemented
        return (
            self.entity_type == other.entity_type and self.entity_id == other.entity_id
        )


@dataclass
class EntityNode:
    """A node representing an entity in the claim-to-graph projection.

    Used for projecting memory claims to graph entities with properties.
    """

    entity_id: int
    entity_type: str
    canonical_name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationshipEdge:
    """An edge representing a relationship between entities in the claim-to-graph projection.

    Used for projecting memory claims with object_entity_id to graph relationships.
    """

    source_entity_id: int
    target_entity_id: int
    relationship_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    """An ordered traversal path through the entity graph.

    ``nodes`` and ``edges`` are parallel sequences where ``edges[i]``
    connects ``nodes[i]`` to ``nodes[i+1]``.
    """

    nodes: list[GraphNode]
    edges: list[EdgeRecord]
    total_confidence: float = 1.0

    def __len__(self) -> int:
        return len(self.edges)

    @property
    def is_empty(self) -> bool:
        return len(self.nodes) == 0

    @property
    def start(self) -> GraphNode | None:
        return self.nodes[0] if self.nodes else None

    @property
    def end(self) -> GraphNode | None:
        return self.nodes[-1] if self.nodes else None
