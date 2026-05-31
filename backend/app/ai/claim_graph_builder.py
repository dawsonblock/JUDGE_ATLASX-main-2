"""Builds a claim-level graph for an entity integrating contradictions and timeline.

All rule-based — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim

# ---------------------------------------------------------------------------
# Node and graph types
# ---------------------------------------------------------------------------


@dataclass
class ClaimNode:
    claim_id: int
    claim_type: str
    confidence: float
    timestamp: Optional[datetime]


@dataclass
class ClaimGraph:
    entity_id: int
    nodes: list[ClaimNode]
    # edges: (claim_id_a, claim_id_b, relation) — "supports" | "contradicts" | "precedes"
    edges: list[tuple[int, int, str]]
    contradiction_pairs: list[tuple[int, int]]
    timeline_order: list[int]  # claim_ids ordered chronologically (oldest first)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_timestamp(claim: MemoryClaim) -> Optional[datetime]:
    for attr in ("last_seen_at", "updated_at", "created_at"):
        val = getattr(claim, attr, None)
        if val is not None:
            return val
    return None


def _claims_to_nodes(claims: list[MemoryClaim]) -> list[ClaimNode]:
    nodes: list[ClaimNode] = []
    for c in claims:
        nodes.append(
            ClaimNode(
                claim_id=c.id,
                claim_type=c.claim_type,
                confidence=float(c.confidence or 0.0),
                timestamp=_extract_timestamp(c),
            )
        )
    return nodes


def _build_timeline_order(nodes: list[ClaimNode]) -> list[int]:
    """Return claim_ids sorted chronologically (nones last)."""

    def sort_key(n: ClaimNode):
        return n.timestamp or datetime.max

    return [n.claim_id for n in sorted(nodes, key=sort_key)]


def _build_contradiction_edges(
    contradiction_pairs: list[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    return [(a, b, "contradicts") for a, b in contradiction_pairs]


def _build_support_edges(nodes: list[ClaimNode]) -> list[tuple[int, int, str]]:
    """Pair nodes of the same claim_type that are NOT contradictions as 'supports'."""
    type_map: dict[str, list[int]] = {}
    for node in nodes:
        type_map.setdefault(node.claim_type, []).append(node.claim_id)

    edges: list[tuple[int, int, str]] = []
    for ids in type_map.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                edges.append((ids[i], ids[j], "supports"))
    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_claim_graph(db: Session, entity_id: int) -> ClaimGraph:
    """Build a full claim graph for *entity_id*."""
    from app.ai.contradiction_engine import (
        detect_contradictions,
    )  # local to avoid cycle

    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )

    nodes = _claims_to_nodes(claims)
    timeline = _build_timeline_order(nodes)

    contradiction_results = detect_contradictions(db, entity_id)
    contradiction_pairs = [(r.claim_id_a, r.claim_id_b) for r in contradiction_results]

    contradiction_pair_set: set[tuple[int, int]] = set(
        (min(a, b), max(a, b)) for a, b in contradiction_pairs
    )

    # Support edges — only for pairs NOT in contradiction set
    raw_support = _build_support_edges(nodes)
    support_edges = [
        (a, b, rel)
        for a, b, rel in raw_support
        if (min(a, b), max(a, b)) not in contradiction_pair_set
    ]

    contradiction_edges = _build_contradiction_edges(contradiction_pairs)

    return ClaimGraph(
        entity_id=entity_id,
        nodes=nodes,
        edges=support_edges + contradiction_edges,
        contradiction_pairs=contradiction_pairs,
        timeline_order=timeline,
    )


def find_supporting(graph: ClaimGraph, claim_id: int) -> list[int]:
    """Return claim_ids that support *claim_id* (same type, no contradiction)."""
    contradiction_set: set[tuple[int, int]] = {
        (min(a, b), max(a, b)) for a, b in graph.contradiction_pairs
    }
    # Find same-type peers
    target_type = next(
        (n.claim_type for n in graph.nodes if n.claim_id == claim_id), None
    )
    if target_type is None:
        return []

    peers = [
        n.claim_id
        for n in graph.nodes
        if n.claim_type == target_type and n.claim_id != claim_id
    ]
    return [
        p
        for p in peers
        if (min(claim_id, p), max(claim_id, p)) not in contradiction_set
    ]


def find_conflicting(graph: ClaimGraph, claim_id: int) -> list[int]:
    """Return claim_ids that contradict *claim_id*."""
    return [
        b if a == claim_id else a
        for a, b in graph.contradiction_pairs
        if claim_id in (a, b)
    ]
