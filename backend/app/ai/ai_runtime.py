"""High-level façade that wires together all AI reasoning sub-modules.

Usage:
    runtime = AIRuntime(db)
    trust = runtime.compute_trust(entity_id=42)
    graph = runtime.build_claim_graph(entity_id=42)
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.ai.claim_graph_builder import ClaimGraph, build_claim_graph
from app.ai.claim_linker import ClaimLink, link_claim_to_entity
from app.ai.confidence_engine import ConfidenceScore, score_claim, score_entity
from app.ai.contradiction_engine import ContradictionResult, detect_contradictions
from app.ai.entity_resolution import ResolutionCandidate, find_candidates
from app.ai.narrative_detection import NarrativeMatch, detect_narratives
from app.ai.source_bias_analysis import BiasReport, analyze_source_text
from app.ai.temporal_reasoner import TemporalSequence, build_sequence
from app.ai.trust_propagation import (
    TrustScore,
    compute_trust,
    get_trust_tier,
    propagate_trust,
)


class AIRuntime:
    """Unified entry point for all deterministic AI reasoning operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Contradiction
    # ------------------------------------------------------------------

    def detect_contradictions(self, entity_id: int) -> list[ContradictionResult]:
        return detect_contradictions(self._db, entity_id)

    # ------------------------------------------------------------------
    # Trust
    # ------------------------------------------------------------------

    def compute_trust(self, entity_id: int) -> TrustScore:
        return compute_trust(self._db, entity_id)

    def propagate_trust(self, entity_id: int, depth: int = 3) -> list[TrustScore]:
        return propagate_trust(self._db, entity_id, depth=depth)

    @staticmethod
    def get_trust_tier(score: float) -> str:
        return get_trust_tier(score)

    # ------------------------------------------------------------------
    # Claim graph
    # ------------------------------------------------------------------

    def build_claim_graph(self, entity_id: int) -> ClaimGraph:
        return build_claim_graph(self._db, entity_id)

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def score_entity(self, entity_id: int) -> ConfidenceScore:
        return score_entity(self._db, entity_id)

    def score_claim(self, claim_id: int) -> ConfidenceScore:
        return score_claim(self._db, claim_id)

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------

    def detect_narratives(self, entity_id: int) -> list[NarrativeMatch]:
        return detect_narratives(self._db, entity_id)

    # ------------------------------------------------------------------
    # Source bias
    # ------------------------------------------------------------------

    @staticmethod
    def analyze_source_bias(text: str, source_name: str) -> BiasReport:
        return analyze_source_text(text, source_name)

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------

    def resolve_entities(
        self, entity_id: int, threshold: float = 0.80
    ) -> list[ResolutionCandidate]:
        return find_candidates(self._db, entity_id, threshold=threshold)

    # ------------------------------------------------------------------
    # Temporal
    # ------------------------------------------------------------------

    def build_temporal_sequence(self, entity_id: int) -> TemporalSequence:
        return build_sequence(self._db, entity_id)

    # ------------------------------------------------------------------
    # Claim linking
    # ------------------------------------------------------------------

    def link_claim(self, claim_id: int) -> Optional[ClaimLink]:
        return link_claim_to_entity(self._db, claim_id)
