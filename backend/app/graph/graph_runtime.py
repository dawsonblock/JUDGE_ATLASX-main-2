"""Top-level graph runtime container.

Wires all graph components together and exposes them as a single
dependency-injectable object.  Intended for use in FastAPI dependencies::

    def get_graph_runtime(db: Session = Depends(get_db)) -> GraphRuntime:
        return GraphRuntime(db)

No LLM calls.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.graph.entity_registry import EntityRegistry, get_registry
from app.graph.graph_queries import GraphQueryEngine
from app.graph.graph_resolver import GraphResolver
from app.graph.temporal_chain import TemporalChain


class GraphRuntime:
    """Wires all graph components for a single request/session lifecycle.

    Each component is scoped to the provided SQLAlchemy session; the
    EntityRegistry is a process-global singleton.

    Attributes:
        db:       The SQLAlchemy session this runtime is bound to.
        registry: Process-global LRU entity cache.
        queries:  Low-level edge read/write engine.
        resolver: High-level canonical entity resolver.
        temporal: Temporal edge chain reconstruction.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.registry: EntityRegistry = get_registry()
        self.queries: GraphQueryEngine = GraphQueryEngine(db)
        self.resolver: GraphResolver = GraphResolver(db)
        self.temporal: TemporalChain = TemporalChain(db)

    def refresh_registry(self, entity_id: int) -> None:
        """Invalidate the cached entry for *entity_id*.

        Call this after any update to a CanonicalEntity row so that the
        next ``registry.get()`` re-fetches from the database.

        Args:
            entity_id: Primary key of the CanonicalEntity to invalidate.
        """
        self.registry.invalidate(entity_id)

    def clear_registry(self) -> None:
        """Remove all entries from the process-global entity cache.

        Typically only needed during large bulk-import operations or tests.
        """
        self.registry.clear()
