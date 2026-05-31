"""Tests for the Phase C AI Reasoning Runtime.

All tests use MagicMock DBs — no live database required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim(
    id: int = 1,
    claim_type: str = "bail_amount",
    claim_value: str = "10000",
    entity_id: int = 1,
    is_active: bool = True,
    confidence: float = 0.75,
    source_snapshot_id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = id
    c.claim_type = claim_type
    c.claim_value = claim_value
    c.claim_value_json = None
    c.entity_id = entity_id
    c.is_active = is_active
    c.confidence = confidence
    c.source_snapshot_id = source_snapshot_id
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    c.created_at = created_at or now
    c.updated_at = updated_at or now
    c.last_seen_at = last_seen_at
    return c


def _make_entity(
    id: int = 1,
    canonical_name: str = "John Smith",
    entity_type: str = "person",
    confidence_score: float = 0.70,
    status: str = "active",
    merged_into_id: int | None = None,
    canonical_id_external: str | None = None,
) -> MagicMock:
    e = MagicMock()
    e.id = id
    e.canonical_name = canonical_name
    e.entity_type = entity_type
    e.confidence_score = confidence_score
    e.status = status
    e.merged_into_id = merged_into_id
    e.canonical_id_external = canonical_id_external
    e.source_records = []
    return e


def _db_with_claims(claims: list) -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = claims
    q.limit.return_value = q
    q.first.return_value = claims[0] if claims else None
    db.query.return_value = q
    return db


# ===========================================================================
# contradiction_engine
# ===========================================================================


class TestContradictionEngine:
    from app.ai.contradiction_engine import (
        RESOLUTION_A_WINS,
        RESOLUTION_B_WINS,
        RESOLUTION_UNRESOLVED,
        ContradictionResult,
        detect_contradictions,
        get_unresolved,
        resolve_contradiction,
    )

    def test_import(self):
        from app.ai.contradiction_engine import ContradictionResult

        assert ContradictionResult

    def test_no_claims_returns_empty(self):
        from app.ai.contradiction_engine import detect_contradictions

        db = _db_with_claims([])
        assert detect_contradictions(db, entity_id=1) == []

    def test_single_claim_no_contradiction(self):
        from app.ai.contradiction_engine import detect_contradictions

        db = _db_with_claims([_make_claim()])
        assert detect_contradictions(db, entity_id=1) == []

    def test_two_identical_values_no_contradiction(self):
        from app.ai.contradiction_engine import detect_contradictions

        c1 = _make_claim(id=1, claim_value="10000")
        c2 = _make_claim(id=2, claim_value="10000")
        db = _db_with_claims([c1, c2])
        assert detect_contradictions(db, entity_id=1) == []

    def test_two_different_bail_values_yields_contradiction(self):
        from app.ai.contradiction_engine import detect_contradictions

        c1 = _make_claim(id=1, claim_type="bail_amount", claim_value="10000")
        c2 = _make_claim(id=2, claim_type="bail_amount", claim_value="500000")
        db = _db_with_claims([c1, c2])
        results = detect_contradictions(db, entity_id=1)
        assert len(results) == 1
        assert results[0].claim_id_a in (1, 2)
        assert results[0].claim_id_b in (1, 2)

    def test_non_contradictable_type_ignored(self):
        from app.ai.contradiction_engine import detect_contradictions

        c1 = _make_claim(id=1, claim_type="biography", claim_value="foo")
        c2 = _make_claim(id=2, claim_type="biography", claim_value="bar")
        db = _db_with_claims([c1, c2])
        assert detect_contradictions(db, entity_id=1) == []

    def test_contradiction_result_has_confidence(self):
        from app.ai.contradiction_engine import detect_contradictions

        c1 = _make_claim(id=1, claim_type="release_decision", claim_value="released")
        c2 = _make_claim(id=2, claim_type="release_decision", claim_value="detained")
        db = _db_with_claims([c1, c2])
        r = detect_contradictions(db, entity_id=1)
        assert len(r) == 1
        assert 0.0 < r[0].confidence <= 1.0

    def test_contradiction_result_frozen(self):
        from app.ai.contradiction_engine import ContradictionResult

        cr = ContradictionResult(1, 2, 1, "bail_amount", "100", "200", 0.8, None)
        with pytest.raises((AttributeError, TypeError)):
            cr.confidence = 0.5  # type: ignore

    def test_resolve_contradiction_a_wins(self):
        from app.ai.contradiction_engine import (
            RESOLUTION_A_WINS,
            ContradictionResult,
            resolve_contradiction,
        )

        cr = ContradictionResult(1, 2, 1, "bail_amount", "100", "200", 0.9, None)
        claim_b = _make_claim(id=2)
        db = MagicMock()
        db.get.return_value = claim_b
        resolve_contradiction(db, cr, RESOLUTION_A_WINS)
        assert claim_b.is_active is False

    def test_get_unresolved_returns_list(self):
        from app.ai.contradiction_engine import get_unresolved

        c1 = _make_claim(id=1, claim_type="bail_amount", claim_value="100")
        c2 = _make_claim(id=2, claim_type="bail_amount", claim_value="200")
        db = _db_with_claims([c1, c2])
        # get_unresolved queries ALL entities so mock accordingly
        entity_q = MagicMock()
        entity_q.filter.return_value = entity_q
        entity_q.all.return_value = []  # no entities → no contradictions
        db.query.return_value = entity_q
        result = get_unresolved(db)
        assert isinstance(result, list)


# ===========================================================================
# trust_propagation
# ===========================================================================


class TestTrustPropagation:
    def test_import(self):
        from app.ai.trust_propagation import TrustScore

        assert TrustScore

    def test_get_trust_tier_high(self):
        from app.ai.trust_propagation import get_trust_tier

        assert get_trust_tier(0.90) == "high"

    def test_get_trust_tier_medium(self):
        from app.ai.trust_propagation import get_trust_tier

        assert get_trust_tier(0.65) == "medium"

    def test_get_trust_tier_low(self):
        from app.ai.trust_propagation import get_trust_tier

        assert get_trust_tier(0.40) == "low"

    def test_get_trust_tier_untrusted(self):
        from app.ai.trust_propagation import get_trust_tier

        assert get_trust_tier(0.10) == "untrusted"

    def test_compute_trust_returns_score(self):
        from app.ai.trust_propagation import compute_trust

        entity = _make_entity(confidence_score=0.75)
        db = MagicMock()
        db.get.return_value = entity
        edge_q = MagicMock()
        edge_q.filter.return_value = edge_q
        edge_q.all.return_value = []
        db.query.return_value = edge_q
        ts = compute_trust(db, entity_id=1)
        assert 0.0 <= ts.score <= 1.0

    def test_compute_trust_missing_entity(self):
        from app.ai.trust_propagation import compute_trust

        db = MagicMock()
        db.get.return_value = None
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        ts = compute_trust(db, entity_id=999)
        # entity absent → default base trust 0.5, no edge bonus
        assert ts.entity_id == 999
        assert 0.0 <= ts.score <= 1.0

    def test_propagate_trust_empty(self):
        from app.ai.trust_propagation import propagate_trust

        entity = _make_entity()
        db = MagicMock()
        db.get.return_value = entity
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        results = propagate_trust(db, source_entity_id=1, depth=1)
        assert isinstance(results, list)

    def test_trust_score_frozen(self):
        from app.ai.trust_propagation import TrustScore

        ts = TrustScore(1, 0.5, [], 0.85, datetime.now(timezone.utc))
        with pytest.raises((AttributeError, TypeError)):
            ts.score = 0.9  # type: ignore

    def test_trust_decay_constant(self):
        from app.ai.trust_propagation import TRUST_DECAY

        assert TRUST_DECAY == 0.85


# ===========================================================================
# claim_linker
# ===========================================================================


class TestClaimLinker:
    def test_import(self):
        from app.ai.claim_linker import ClaimLink

        assert ClaimLink

    def test_link_missing_claim(self):
        from app.ai.claim_linker import link_claim_to_entity

        db = MagicMock()
        db.get.return_value = None
        result = link_claim_to_entity(db, claim_id=99)
        assert result is None

    def test_link_no_entities(self):
        from app.ai.claim_linker import link_claim_to_entity

        claim = _make_claim(claim_value="John Smith")
        claim.entity_id = None  # unlinked claim so self-ref path is not taken
        db = MagicMock()
        db.get.return_value = claim
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        result = link_claim_to_entity(db, claim_id=1)
        assert result is None

    def test_link_exact_name_match(self):
        from app.ai.claim_linker import link_claim_to_entity

        claim = _make_claim(claim_value="john smith")
        entity = _make_entity(canonical_name="john smith")
        db = MagicMock()
        db.get.return_value = claim
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [entity]
        db.query.return_value = q
        result = link_claim_to_entity(db, claim_id=1)
        assert result is not None
        assert result.entity_id == 1

    def test_get_entity_claims_returns_list(self):
        from app.ai.claim_linker import get_entity_claims

        c = _make_claim()
        db = _db_with_claims([c])
        results = get_entity_claims(db, entity_id=1)
        assert isinstance(results, list)

    def test_bulk_link_empty(self):
        from app.ai.claim_linker import bulk_link_unlinked

        db = _db_with_claims([])
        results = bulk_link_unlinked(db, limit=10)
        assert results == []

    def test_claim_link_frozen(self):
        from app.ai.claim_linker import ClaimLink

        cl = ClaimLink(1, 2, "exact_name", 0.95)
        with pytest.raises((AttributeError, TypeError)):
            cl.confidence = 0.1  # type: ignore


# ===========================================================================
# temporal_reasoner
# ===========================================================================


class TestTemporalReasoner:
    def test_import(self):
        from app.ai.temporal_reasoner import TemporalGap, TemporalSequence

        assert TemporalGap and TemporalSequence

    def test_build_sequence_empty(self):
        from app.ai.temporal_reasoner import build_sequence

        db = _db_with_claims([])
        seq = build_sequence(db, entity_id=1)
        assert seq.entity_id == 1
        assert seq.events == []

    def test_detect_gaps_no_gap(self):
        from app.ai.temporal_reasoner import detect_gaps

        events = [
            {"claim_id": 1, "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"claim_id": 2, "timestamp": datetime(2024, 1, 10, tzinfo=timezone.utc)},
        ]
        gaps = detect_gaps(events, min_gap_days=30)
        assert gaps == []

    def test_detect_gaps_finds_gap(self):
        from app.ai.temporal_reasoner import detect_gaps

        events = [
            {"claim_id": 1, "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"claim_id": 2, "timestamp": datetime(2024, 6, 1, tzinfo=timezone.utc)},
        ]
        gaps = detect_gaps(events, min_gap_days=30)
        assert len(gaps) == 1
        assert gaps[0].gap_days > 30

    def test_is_chronologically_consistent_ordered(self):
        from app.ai.temporal_reasoner import is_chronologically_consistent

        events = [
            {"claim_id": 1, "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"claim_id": 2, "timestamp": datetime(2024, 2, 1, tzinfo=timezone.utc)},
        ]
        assert is_chronologically_consistent(events) is True

    def test_is_chronologically_consistent_unordered(self):
        from app.ai.temporal_reasoner import is_chronologically_consistent

        events = [
            {"claim_id": 1, "timestamp": datetime(2024, 6, 1, tzinfo=timezone.utc)},
            {"claim_id": 2, "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        ]
        assert is_chronologically_consistent(events) is False

    def test_temporal_gap_frozen(self):
        from app.ai.temporal_reasoner import TemporalGap

        g = TemporalGap(None, None, 45)
        with pytest.raises((AttributeError, TypeError)):
            g.gap_days = 10  # type: ignore


# ===========================================================================
# confidence_engine
# ===========================================================================


class TestConfidenceEngine:
    def test_import(self):
        from app.ai.confidence_engine import ConfidenceScore, QUALITY_WEIGHTS

        assert ConfidenceScore and QUALITY_WEIGHTS

    def test_apply_corroboration_bonus_single_source(self):
        from app.ai.confidence_engine import apply_corroboration_bonus

        # Returns the bonus value only (not base+bonus); 1 source → no bonus
        assert apply_corroboration_bonus(0.70, 1) == 0.0

    def test_apply_corroboration_bonus_two_sources(self):
        from app.ai.confidence_engine import apply_corroboration_bonus

        # 2 sources → small positive bonus
        assert apply_corroboration_bonus(0.70, 2) > 0.0

    def test_apply_corroboration_caps_at_one(self):
        from app.ai.confidence_engine import apply_corroboration_bonus

        result = apply_corroboration_bonus(0.99, 100)
        assert result <= 1.0

    def test_score_claim_missing(self):
        from app.ai.confidence_engine import score_claim

        db = MagicMock()
        db.get.return_value = None
        result = score_claim(db, claim_id=99)
        assert result.score == 0.0

    def test_score_claim_no_snapshot(self):
        from app.ai.confidence_engine import score_claim

        claim = _make_claim(confidence=0.80, source_snapshot_id=None)
        db = MagicMock()
        db.get.return_value = claim
        result = score_claim(db, claim_id=1)
        assert 0.0 <= result.score <= 1.0

    def test_score_entity_no_claims(self):
        from app.ai.confidence_engine import score_entity

        db = _db_with_claims([])
        result = score_entity(db, entity_id=1)
        assert result.score == 0.0
        assert result.source_count == 0

    def test_confidence_score_frozen(self):
        from app.ai.confidence_engine import ConfidenceScore

        cs = ConfidenceScore(1, "claim", 0.7, 1, 0.0, 0.7)
        with pytest.raises((AttributeError, TypeError)):
            cs.score = 0.5  # type: ignore

    def test_quality_weights_court_record(self):
        from app.ai.confidence_engine import QUALITY_WEIGHTS

        assert QUALITY_WEIGHTS["court_record"] == 1.0

    def test_quality_weights_social_lower_than_news(self):
        from app.ai.confidence_engine import QUALITY_WEIGHTS

        assert QUALITY_WEIGHTS["social"] < QUALITY_WEIGHTS["news"]


# ===========================================================================
# entity_resolution
# ===========================================================================


class TestEntityResolution:
    def test_import(self):
        from app.ai.entity_resolution import ResolutionCandidate

        assert ResolutionCandidate

    def test_find_candidates_missing_entity(self):
        from app.ai.entity_resolution import find_candidates

        db = MagicMock()
        db.get.return_value = None
        assert find_candidates(db, entity_id=99) == []

    def test_find_candidates_no_peers(self):
        from app.ai.entity_resolution import find_candidates

        entity = _make_entity()
        db = MagicMock()
        db.get.return_value = entity
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        assert find_candidates(db, entity_id=1) == []

    def test_find_candidates_exact_name_merge(self):
        from app.ai.entity_resolution import MERGE, find_candidates

        target = _make_entity(id=1, canonical_name="John Smith")
        peer = _make_entity(id=2, canonical_name="John Smith")
        db = MagicMock()
        db.get.return_value = target
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [peer]
        db.query.return_value = q
        results = find_candidates(db, entity_id=1, threshold=0.80)
        assert any(r.resolution == MERGE for r in results)

    def test_find_candidates_dissimilar_distinct(self):
        from app.ai.entity_resolution import DISTINCT, UNCERTAIN, find_candidates

        target = _make_entity(id=1, canonical_name="Alpha Bravo")
        peer = _make_entity(id=2, canonical_name="Zebra Yacht")
        db = MagicMock()
        db.get.return_value = target
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [peer]
        db.query.return_value = q
        results = find_candidates(db, entity_id=1, threshold=0.80)
        # dissimilar -> DISTINCT or not surfaced
        for r in results:
            assert r.resolution in (DISTINCT, UNCERTAIN)

    def test_resolve_candidate_non_merge_noop(self):
        from app.ai.entity_resolution import (
            UNCERTAIN,
            ResolutionCandidate,
            resolve_candidate,
        )

        cand = ResolutionCandidate(1, 2, 0.50, [], UNCERTAIN)
        db = MagicMock()
        result = resolve_candidate(db, cand)
        assert result is False

    def test_resolve_candidate_merge(self):
        from app.ai.entity_resolution import (
            MERGE,
            ResolutionCandidate,
            resolve_candidate,
        )

        cand = ResolutionCandidate(1, 2, 0.95, ["canonical_name"], MERGE)
        entity_b = _make_entity(id=2)
        db = MagicMock()
        db.get.return_value = entity_b
        result = resolve_candidate(db, cand)
        assert result is True
        assert entity_b.status == "merged_into"
        assert entity_b.merged_into_id == 1

    def test_candidate_frozen(self):
        from app.ai.entity_resolution import MERGE, ResolutionCandidate

        rc = ResolutionCandidate(1, 2, 0.9, [], MERGE)
        with pytest.raises((AttributeError, TypeError)):
            rc.similarity = 0.1  # type: ignore


# ===========================================================================
# narrative_detection
# ===========================================================================


class TestNarrativeDetection:
    def test_import(self):
        from app.ai.narrative_detection import NarrativeMatch

        assert NarrativeMatch

    def test_detect_from_text_exoneration(self):
        from app.ai.narrative_detection import detect_from_text

        # Need enough phrase hits to exceed MIN_MATCH_CONFIDENCE=0.30 (9 phrases → need 3+)
        text = "acquitted, not guilty, case dismissed"
        results = detect_from_text(text, entity_id=1)
        names = [r.pattern_name for r in results]
        assert "exoneration" in names

    def test_detect_from_text_no_match(self):
        from app.ai.narrative_detection import detect_from_text

        results = detect_from_text("The weather was nice today.", entity_id=1)
        assert results == []

    def test_detect_from_text_repeat_offender(self):
        from app.ai.narrative_detection import detect_from_text

        # Need 3+ hits out of 7 phrases to exceed MIN_MATCH_CONFIDENCE=0.30
        text = (
            "prior conviction noted; repeat offender with a criminal history on record."
        )
        results = detect_from_text(text, entity_id=1)
        names = [r.pattern_name for r in results]
        assert "repeat_offender" in names

    def test_detect_narratives_empty_claims(self):
        from app.ai.narrative_detection import detect_narratives

        db = _db_with_claims([])
        assert detect_narratives(db, entity_id=1) == []

    def test_detect_narratives_flight_risk(self):
        from app.ai.narrative_detection import detect_narratives

        claim = _make_claim(
            claim_value="subject is considered a flight risk and failed to appear"
        )
        db = _db_with_claims([claim])
        results = detect_narratives(db, entity_id=1)
        names = [r.pattern_name for r in results]
        assert "flight_risk" in names

    def test_narrative_match_confidence_range(self):
        from app.ai.narrative_detection import detect_from_text

        results = detect_from_text(
            "charges dropped and wrongful conviction found", entity_id=1
        )
        for r in results:
            assert 0.0 < r.confidence <= 1.0

    def test_narrative_match_frozen(self):
        from app.ai.narrative_detection import NarrativeMatch

        nm = NarrativeMatch(1, "exoneration", 0.7, [], [])
        with pytest.raises((AttributeError, TypeError)):
            nm.confidence = 0.1  # type: ignore


# ===========================================================================
# source_bias_analysis
# ===========================================================================


class TestSourceBiasAnalysis:
    def test_import(self):
        from app.ai.source_bias_analysis import BiasReport

        assert BiasReport

    def test_analyze_no_bias(self):
        from app.ai.source_bias_analysis import analyze_source_text

        report = analyze_source_text("The court ruled on the matter.", "Court Times")
        assert report.bias_type is None or report.indicator_count == 0

    def test_analyze_prosecutorial(self):
        from app.ai.source_bias_analysis import analyze_source_text

        text = "The defendant is a dangerous offender and career criminal with depraved indifference."
        report = analyze_source_text(text, "DA Office")
        assert report.bias_type == "prosecutorial"
        assert report.indicator_count >= 2

    def test_analyze_sensationalist(self):
        from app.ai.source_bias_analysis import analyze_source_text

        text = "The shocking and horrific monster is a predator who committed a heinous crime."
        report = analyze_source_text(text, "Tabloid")
        assert report.bias_type == "sensationalist"

    def test_analyze_defense_bias(self):
        from app.ai.source_bias_analysis import analyze_source_text

        text = "He was wrongfully accused; witnesses testified to his no prior record and family man character."
        report = analyze_source_text(text, "Defense Outlet")
        assert report.bias_type == "defense"

    def test_bias_report_confidence_range(self):
        from app.ai.source_bias_analysis import analyze_source_text

        text = "Shocking monster predator"
        report = analyze_source_text(text, "X")
        if report.bias_type:
            assert 0.0 < report.confidence <= 1.0

    def test_bias_report_frozen(self):
        from app.ai.source_bias_analysis import BiasReport

        br = BiasReport("src", "sensationalist", 0.8, 3, [])
        with pytest.raises((AttributeError, TypeError)):
            br.confidence = 0.1  # type: ignore

    def test_get_source_bias_profile_no_snapshots(self):
        from app.ai.source_bias_analysis import get_source_bias_profile

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        results = get_source_bias_profile(db, source_name="Unknown")
        assert results == []


# ===========================================================================
# claim_graph_builder
# ===========================================================================


class TestClaimGraphBuilder:
    def test_import(self):
        from app.ai.claim_graph_builder import ClaimGraph, ClaimNode

        assert ClaimGraph and ClaimNode

    def test_build_graph_no_claims(self):
        from app.ai.claim_graph_builder import build_claim_graph

        db = _db_with_claims([])
        # detect_contradictions also uses db.query
        graph = build_claim_graph(db, entity_id=1)
        assert graph.entity_id == 1
        assert graph.nodes == []

    def test_build_graph_single_claim(self):
        from app.ai.claim_graph_builder import build_claim_graph

        claim = _make_claim(id=1, claim_type="bail_amount", claim_value="10000")
        db = _db_with_claims([claim])
        graph = build_claim_graph(db, entity_id=1)
        assert len(graph.nodes) == 1
        assert graph.nodes[0].claim_id == 1

    def test_find_supporting_empty_graph(self):
        from app.ai.claim_graph_builder import ClaimGraph, find_supporting

        g = ClaimGraph(
            entity_id=1, nodes=[], edges=[], contradiction_pairs=[], timeline_order=[]
        )
        assert find_supporting(g, claim_id=99) == []

    def test_find_conflicting_empty_graph(self):
        from app.ai.claim_graph_builder import ClaimGraph, find_conflicting

        g = ClaimGraph(
            entity_id=1, nodes=[], edges=[], contradiction_pairs=[], timeline_order=[]
        )
        assert find_conflicting(g, claim_id=99) == []

    def test_find_conflicting_pair(self):
        from app.ai.claim_graph_builder import ClaimGraph, ClaimNode, find_conflicting

        nodes = [
            ClaimNode(1, "bail_amount", 0.9, None),
            ClaimNode(2, "bail_amount", 0.8, None),
        ]
        g = ClaimGraph(
            entity_id=1,
            nodes=nodes,
            edges=[(1, 2, "contradicts")],
            contradiction_pairs=[(1, 2)],
            timeline_order=[1, 2],
        )
        assert find_conflicting(g, claim_id=1) == [2]

    def test_find_supporting_same_type(self):
        from app.ai.claim_graph_builder import ClaimGraph, ClaimNode, find_supporting

        nodes = [
            ClaimNode(1, "jurisdiction", 0.9, None),
            ClaimNode(2, "jurisdiction", 0.8, None),
        ]
        g = ClaimGraph(
            entity_id=1,
            nodes=nodes,
            edges=[(1, 2, "supports")],
            contradiction_pairs=[],
            timeline_order=[1, 2],
        )
        assert 2 in find_supporting(g, claim_id=1)

    def test_timeline_order_populated(self):
        from app.ai.claim_graph_builder import build_claim_graph

        c1 = _make_claim(id=1, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        c2 = _make_claim(id=2, created_at=datetime(2024, 3, 1, tzinfo=timezone.utc))
        db = _db_with_claims([c1, c2])
        graph = build_claim_graph(db, entity_id=1)
        assert len(graph.timeline_order) == 2


# ===========================================================================
# ai_runtime (façade)
# ===========================================================================


class TestAIRuntime:
    def test_import(self):
        from app.ai.ai_runtime import AIRuntime

        assert AIRuntime

    def test_instantiate(self):
        from app.ai.ai_runtime import AIRuntime

        db = MagicMock()
        runtime = AIRuntime(db)
        assert runtime is not None

    def test_get_trust_tier_static(self):
        from app.ai.ai_runtime import AIRuntime

        assert AIRuntime.get_trust_tier(0.85) == "high"

    def test_analyze_source_bias_static(self):
        from app.ai.ai_runtime import AIRuntime

        report = AIRuntime.analyze_source_bias("shocking monster predator", "Tabloid")
        assert report.bias_type is not None

    def test_detect_contradictions_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        db = _db_with_claims([])
        runtime = AIRuntime(db)
        result = runtime.detect_contradictions(entity_id=1)
        assert isinstance(result, list)

    def test_detect_narratives_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        db = _db_with_claims([])
        runtime = AIRuntime(db)
        result = runtime.detect_narratives(entity_id=1)
        assert isinstance(result, list)

    def test_score_entity_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        db = _db_with_claims([])
        runtime = AIRuntime(db)
        result = runtime.score_entity(entity_id=1)
        assert result.score == 0.0

    def test_build_temporal_sequence_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        db = _db_with_claims([])
        runtime = AIRuntime(db)
        seq = runtime.build_temporal_sequence(entity_id=1)
        assert seq.entity_id == 1

    def test_resolve_entities_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        entity = _make_entity()
        db = MagicMock()
        db.get.return_value = entity
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        runtime = AIRuntime(db)
        result = runtime.resolve_entities(entity_id=1)
        assert isinstance(result, list)

    def test_link_claim_delegates(self):
        from app.ai.ai_runtime import AIRuntime

        db = MagicMock()
        db.get.return_value = None
        runtime = AIRuntime(db)
        result = runtime.link_claim(claim_id=99)
        assert result is None
