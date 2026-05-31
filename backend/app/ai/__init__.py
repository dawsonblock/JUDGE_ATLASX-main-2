"""Deterministic AI-assist layer for ingestion and review drafts."""

# Phase C — AI Reasoning Runtime
from app.ai.ai_runtime import AIRuntime
from app.ai.claim_graph_builder import (
    ClaimGraph,
    ClaimNode,
    build_claim_graph,
    find_conflicting,
    find_supporting,
)
from app.ai.claim_linker import (
    ClaimLink,
    bulk_link_unlinked,
    get_entity_claims,
    link_claim_to_entity,
)
from app.ai.confidence_engine import (
    ConfidenceScore,
    apply_corroboration_bonus,
    score_claim,
    score_entity,
)
from app.ai.contradiction_engine import (
    ContradictionResult,
    detect_contradictions,
    get_unresolved,
    resolve_contradiction,
)
from app.ai.entity_resolution import (
    ResolutionCandidate,
    bulk_resolve,
    find_candidates,
    resolve_candidate,
)
from app.ai.narrative_detection import (
    NarrativeMatch,
    detect_from_text,
    detect_narratives,
)
from app.ai.source_bias_analysis import (
    BiasReport,
    analyze_source_text,
    get_source_bias_profile,
)
from app.ai.temporal_reasoner import (
    TemporalGap,
    TemporalSequence,
    build_sequence,
    detect_gaps,
    is_chronologically_consistent,
)
from app.ai.trust_propagation import (
    TrustScore,
    compute_trust,
    get_trust_tier,
    propagate_trust,
)

__all__ = [
    # runtime
    "AIRuntime",
    # claim graph
    "ClaimGraph",
    "ClaimNode",
    "build_claim_graph",
    "find_supporting",
    "find_conflicting",
    # claim linker
    "ClaimLink",
    "link_claim_to_entity",
    "bulk_link_unlinked",
    "get_entity_claims",
    # confidence
    "ConfidenceScore",
    "score_claim",
    "score_entity",
    "apply_corroboration_bonus",
    # contradiction
    "ContradictionResult",
    "detect_contradictions",
    "resolve_contradiction",
    "get_unresolved",
    # entity resolution
    "ResolutionCandidate",
    "find_candidates",
    "resolve_candidate",
    "bulk_resolve",
    # narrative
    "NarrativeMatch",
    "detect_narratives",
    "detect_from_text",
    # source bias
    "BiasReport",
    "analyze_source_text",
    "get_source_bias_profile",
    # temporal
    "TemporalGap",
    "TemporalSequence",
    "build_sequence",
    "detect_gaps",
    "is_chronologically_consistent",
    # trust
    "TrustScore",
    "compute_trust",
    "propagate_trust",
    "get_trust_tier",
]
