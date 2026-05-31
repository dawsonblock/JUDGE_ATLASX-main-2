"""Canonical graph authority package.

Provides deterministic entity resolution, typed graph edges,
temporal chain reconstruction, and a unified graph runtime.
"""

from app.graph.canonical_ids import (
    CanonicalIdError,
    generate_canonical_id,
    canonical_id_from_external,
    normalize_entity_name,
)
from app.graph.edge_models import EdgePredicate, EntityType, EdgeKey, EdgeRecord
from app.graph.graph_models import GraphNode, GraphPath, EntityNode, RelationshipEdge
from app.graph.confidence import (
    weighted_confidence,
    decay_confidence,
    merge_confidence,
    propagate_confidence,
)
from app.graph.entity_registry import EntityRegistry, get_registry
from app.graph.graph_merge import (
    MergeResult,
    propose_merge,
    execute_merge,
    resolve_merge_chain,
)
from app.graph.temporal_chain import TemporalEdge, TemporalChain
from app.graph.graph_queries import GraphQueryEngine
from app.graph.graph_resolver import ResolveResult, GraphResolver
from app.graph.graph_runtime import GraphRuntime

__all__ = [
    "CanonicalIdError",
    "decay_confidence",
    "EdgeKey",
    "EdgePredicate",
    "EdgeRecord",
    "EntityNode",
    "EntityRegistry",
    "EntityType",
    "execute_merge",
    "generate_canonical_id",
    "canonical_id_from_external",
    "get_registry",
    "GraphNode",
    "GraphPath",
    "GraphQueryEngine",
    "GraphResolver",
    "GraphRuntime",
    "merge_confidence",
    "MergeResult",
    "normalize_entity_name",
    "propagate_confidence",
    "propose_merge",
    "RelationshipEdge",
    "resolve_merge_chain",
    "ResolveResult",
    "TemporalChain",
    "TemporalEdge",
    "weighted_confidence",
]
