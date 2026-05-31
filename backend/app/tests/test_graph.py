"""Tests for the app.graph package — Phase A.

These tests exercise the pure Python logic that does NOT require a live
database.  DB-dependent classes (GraphQueryEngine, TemporalChain,
GraphResolver, graph_merge) are tested via lightweight in-memory SQLite
or monkeypatched stubs where a real PostgreSQL connection is unavailable.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# canonical_ids
# ---------------------------------------------------------------------------


class TestNormalizeEntityName:
    def test_lowercases(self):
        from app.graph.canonical_ids import normalize_entity_name

        assert normalize_entity_name("SMITH") == "smith"

    def test_strips_punctuation(self):
        from app.graph.canonical_ids import normalize_entity_name

        assert "," not in normalize_entity_name("Smith, J.")

    def test_unicode_nfkc(self):
        from app.graph.canonical_ids import normalize_entity_name

        # "ﬁ" (LATIN SMALL LIGATURE FI) should become "fi"
        result = normalize_entity_name("ﬁle")
        assert result == "file"

    def test_empty_string_raises(self):
        from app.graph.canonical_ids import normalize_entity_name, CanonicalIdError

        with pytest.raises(CanonicalIdError):
            normalize_entity_name("   ")


class TestGenerateCanonicalId:
    def test_deterministic(self):
        from app.graph.canonical_ids import generate_canonical_id

        id1 = generate_canonical_id("judge", "Ruth Bader Ginsburg")
        id2 = generate_canonical_id("judge", "Ruth Bader Ginsburg")
        assert id1 == id2

    def test_different_names_differ(self):
        from app.graph.canonical_ids import generate_canonical_id

        a = generate_canonical_id("judge", "Alice")
        b = generate_canonical_id("judge", "Bob")
        assert a != b

    def test_different_types_differ(self):
        from app.graph.canonical_ids import generate_canonical_id

        a = generate_canonical_id("judge", "Alice")
        b = generate_canonical_id("court", "Alice")
        assert a != b

    def test_returns_16_hex_chars(self):
        from app.graph.canonical_ids import generate_canonical_id

        cid = generate_canonical_id("judge", "Alice")
        assert len(cid) == 16
        int(cid, 16)  # raises ValueError if not valid hex

    def test_invalid_entity_type_raises(self):
        from app.graph.canonical_ids import generate_canonical_id, CanonicalIdError

        with pytest.raises(CanonicalIdError):
            generate_canonical_id("", "Alice")

    def test_invalid_name_raises(self):
        from app.graph.canonical_ids import generate_canonical_id, CanonicalIdError

        with pytest.raises(CanonicalIdError):
            generate_canonical_id("judge", "")


class TestCanonicalIdFromExternal:
    def test_deterministic(self):
        from app.graph.canonical_ids import canonical_id_from_external

        a = canonical_id_from_external("courtlistener", "12345")
        b = canonical_id_from_external("courtlistener", "12345")
        assert a == b

    def test_different_sources_differ(self):
        from app.graph.canonical_ids import canonical_id_from_external

        a = canonical_id_from_external("courtlistener", "12345")
        b = canonical_id_from_external("canlii", "12345")
        assert a != b

    def test_returns_16_hex_chars(self):
        from app.graph.canonical_ids import canonical_id_from_external

        cid = canonical_id_from_external("courtlistener", "abc")
        assert len(cid) == 16


# ---------------------------------------------------------------------------
# edge_models
# ---------------------------------------------------------------------------


class TestEdgePredicate:
    def test_all_values_are_strings(self):
        from app.graph.edge_models import EdgePredicate

        for pred in EdgePredicate:
            assert isinstance(pred.value, str)

    def test_presided_over_exists(self):
        from app.graph.edge_models import EdgePredicate

        assert EdgePredicate.PRESIDED_OVER == "presided_over"


class TestEntityType:
    def test_judge_exists(self):
        from app.graph.edge_models import EntityType

        assert EntityType.JUDGE == "judge"


class TestEdgeRecord:
    def _make_record(self, valid_from, valid_until=None):
        from app.graph.edge_models import EdgeRecord

        return EdgeRecord(
            id=1,
            subject_type="judge",
            subject_id=10,
            predicate="presided_over",
            object_type="case",
            object_id=20,
            evidence_refs={},
            valid_from=valid_from,
            valid_until=valid_until,
            status="active",
            created_by="test",
        )

    def test_is_active_at_open_ended(self):
        now = datetime.now(timezone.utc)
        rec = self._make_record(valid_from=now - timedelta(days=10))
        assert rec.is_active_at(now) is True

    def test_is_active_at_before_valid_from(self):
        now = datetime.now(timezone.utc)
        rec = self._make_record(valid_from=now + timedelta(days=1))
        assert rec.is_active_at(now) is False

    def test_is_active_at_after_valid_until(self):
        now = datetime.now(timezone.utc)
        rec = self._make_record(
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=1),
        )
        assert rec.is_active_at(now) is False

    def test_edge_key(self):
        from app.graph.edge_models import EdgeRecord, EdgeKey

        now = datetime.now(timezone.utc)
        rec = self._make_record(valid_from=now)
        key = rec.key
        assert isinstance(key, EdgeKey)
        assert key.subject_type == "judge"
        assert key.predicate == "presided_over"


# ---------------------------------------------------------------------------
# graph_models
# ---------------------------------------------------------------------------


class TestGraphNode:
    def test_hash_equality_by_type_and_id(self):
        from app.graph.graph_models import GraphNode

        now = datetime.now(timezone.utc)
        n1 = GraphNode(
            entity_type="judge",
            entity_id=1,
            canonical_entity_id=None,
            display_name="Alice",
            confidence=0.9,
        )
        n2 = GraphNode(
            entity_type="judge",
            entity_id=1,
            canonical_entity_id=None,
            display_name="Alice!",
            confidence=0.5,
        )
        assert n1 == n2
        assert hash(n1) == hash(n2)

    def test_different_ids_not_equal(self):
        from app.graph.graph_models import GraphNode

        n1 = GraphNode(
            entity_type="judge",
            entity_id=1,
            canonical_entity_id=None,
            display_name="Alice",
            confidence=0.9,
        )
        n2 = GraphNode(
            entity_type="judge",
            entity_id=2,
            canonical_entity_id=None,
            display_name="Alice",
            confidence=0.9,
        )
        assert n1 != n2


class TestGraphPath:
    def _make_path(self, n_nodes=2, n_edges=1):
        from app.graph.graph_models import GraphNode, GraphPath
        from app.graph.edge_models import EdgeRecord

        now = datetime.now(timezone.utc)
        nodes = [
            GraphNode(
                entity_type="judge",
                entity_id=i,
                canonical_entity_id=None,
                display_name=f"n{i}",
                confidence=0.9,
            )
            for i in range(n_nodes)
        ]
        edges = [
            EdgeRecord(
                id=i,
                subject_type="judge",
                subject_id=i,
                predicate="presided_over",
                object_type="case",
                object_id=i + 10,
                evidence_refs={},
                valid_from=now,
                valid_until=None,
                status="active",
                created_by="test",
            )
            for i in range(n_edges)
        ]
        return GraphPath(nodes=nodes, edges=edges, total_confidence=0.8)

    def test_start_end(self):
        path = self._make_path()
        assert path.start.entity_id == 0
        assert path.end.entity_id == 1

    def test_len(self):
        path = self._make_path(n_nodes=3, n_edges=2)
        assert len(path) == 2

    def test_is_empty_false(self):
        path = self._make_path()
        assert path.is_empty is False

    def test_is_empty_true(self):
        from app.graph.graph_models import GraphPath

        p = GraphPath(nodes=[], edges=[], total_confidence=0.0)
        assert p.is_empty is True


# ---------------------------------------------------------------------------
# confidence
# ---------------------------------------------------------------------------


class TestWeightedConfidence:
    def test_equal_weights(self):
        from app.graph.confidence import weighted_confidence

        result = weighted_confidence([0.8, 0.6, 1.0])
        assert abs(result - 0.8) < 1e-9

    def test_custom_weights(self):
        from app.graph.confidence import weighted_confidence

        result = weighted_confidence([0.0, 1.0], weights=[0.0, 1.0])
        assert abs(result - 1.0) < 1e-9

    def test_clamp_above_one(self):
        from app.graph.confidence import weighted_confidence

        result = weighted_confidence([2.0])
        assert result <= 1.0

    def test_clamp_below_zero(self):
        from app.graph.confidence import weighted_confidence

        result = weighted_confidence([-1.0])
        assert result >= 0.0

    def test_empty_raises(self):
        from app.graph.confidence import weighted_confidence

        with pytest.raises(ValueError):
            weighted_confidence([])


class TestDecayConfidence:
    def test_no_decay_at_zero_days(self):
        from app.graph.confidence import decay_confidence

        result = decay_confidence(1.0, 0)
        assert abs(result - 1.0) < 1e-9

    def test_half_life(self):
        from app.graph.confidence import decay_confidence

        result = decay_confidence(1.0, 365.0, half_life_days=365.0)
        assert abs(result - 0.5) < 1e-9

    def test_decay_is_monotone(self):
        from app.graph.confidence import decay_confidence

        r1 = decay_confidence(1.0, 10)
        r2 = decay_confidence(1.0, 100)
        assert r1 > r2


class TestMergeConfidence:
    def test_geometric_mean_two(self):
        from app.graph.confidence import merge_confidence

        result = merge_confidence([0.25, 1.0])
        assert abs(result - 0.5) < 1e-9

    def test_single_score_unchanged(self):
        from app.graph.confidence import merge_confidence

        assert abs(merge_confidence([0.7]) - 0.7) < 1e-9

    def test_empty_raises(self):
        from app.graph.confidence import merge_confidence

        with pytest.raises(ValueError):
            merge_confidence([])


class TestPropagateConfidence:
    def test_multiply(self):
        from app.graph.confidence import propagate_confidence

        assert abs(propagate_confidence(0.8, 0.5) - 0.4) < 1e-9

    def test_clamp_result(self):
        from app.graph.confidence import propagate_confidence

        assert propagate_confidence(2.0, 2.0) <= 1.0


# ---------------------------------------------------------------------------
# entity_registry
# ---------------------------------------------------------------------------


class TestEntityRegistry:
    def test_singleton(self):
        from app.graph.entity_registry import get_registry

        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_put_and_get(self):
        from app.graph.entity_registry import EntityRegistry

        registry = EntityRegistry(max_size=10)
        mock_entity = MagicMock()
        mock_entity.id = 99
        mock_db = MagicMock()
        registry.put(mock_entity)
        result = registry.get(99, mock_db)
        assert result is mock_entity
        mock_db.get.assert_not_called()  # served from cache

    def test_invalidate(self):
        from app.graph.entity_registry import EntityRegistry

        registry = EntityRegistry(max_size=10)
        mock_entity = MagicMock()
        mock_entity.id = 99
        registry.put(mock_entity)
        registry.invalidate(99)
        assert registry.size == 0

    def test_clear(self):
        from app.graph.entity_registry import EntityRegistry

        registry = EntityRegistry(max_size=10)
        for i in range(5):
            e = MagicMock()
            e.id = i
            registry.put(e)
        registry.clear()
        assert registry.size == 0

    def test_lru_eviction(self):
        from app.graph.entity_registry import EntityRegistry

        registry = EntityRegistry(max_size=3)
        for i in range(4):
            e = MagicMock()
            e.id = i
            registry.put(e)
        assert registry.size == 3
        # oldest (id=0) should be evicted
        mock_db = MagicMock()
        mock_db.get.return_value = None
        assert registry.get(0, mock_db) is None


# ---------------------------------------------------------------------------
# graph_merge (unit — no DB)
# ---------------------------------------------------------------------------


class TestResolveMergeChain:
    def test_active_entity_returns_itself(self):
        from app.graph.graph_merge import resolve_merge_chain

        mock_db = MagicMock()
        entity = MagicMock()
        entity.id = 1
        entity.status = "active"
        entity.merged_into_id = None
        mock_db.get.return_value = entity
        assert resolve_merge_chain(mock_db, 1) == 1

    def test_follows_chain(self):
        from app.graph.graph_merge import resolve_merge_chain

        e1 = MagicMock()
        e1.id = 1
        e1.status = "merged_into"
        e1.merged_into_id = 2

        e2 = MagicMock()
        e2.id = 2
        e2.status = "active"
        e2.merged_into_id = None

        def side_effect(model, pk):
            if pk == 1:
                return e1
            if pk == 2:
                return e2
            return None

        mock_db = MagicMock()
        mock_db.get.side_effect = side_effect
        assert resolve_merge_chain(mock_db, 1) == 2

    def test_cycle_raises(self):
        from app.graph.graph_merge import resolve_merge_chain

        e1 = MagicMock()
        e1.status = "merged_into"
        e1.merged_into_id = 2
        e2 = MagicMock()
        e2.status = "merged_into"
        e2.merged_into_id = 1

        def side_effect(model, pk):
            return e1 if pk == 1 else e2

        mock_db = MagicMock()
        mock_db.get.side_effect = side_effect
        with pytest.raises(ValueError, match="cycle"):
            resolve_merge_chain(mock_db, 1)


# ---------------------------------------------------------------------------
# temporal_chain (unit — no DB)
# ---------------------------------------------------------------------------


class TestTemporalEdge:
    def test_is_open_no_until(self):
        from app.graph.temporal_chain import TemporalEdge
        from app.graph.edge_models import EdgeRecord

        now = datetime.now(timezone.utc)
        rec = EdgeRecord(
            id=1,
            subject_type="j",
            subject_id=1,
            predicate="p",
            object_type="c",
            object_id=2,
            evidence_refs={},
            valid_from=now,
            valid_until=None,
            status="active",
            created_by="test",
        )
        te = TemporalEdge(edge=rec, valid_from=now, valid_until=None)
        assert te.is_open is True

    def test_is_active_at(self):
        from app.graph.temporal_chain import TemporalEdge
        from app.graph.edge_models import EdgeRecord

        now = datetime.now(timezone.utc)
        rec = EdgeRecord(
            id=1,
            subject_type="j",
            subject_id=1,
            predicate="p",
            object_type="c",
            object_id=2,
            evidence_refs={},
            valid_from=now - timedelta(days=5),
            valid_until=None,
            status="active",
            created_by="test",
        )
        te = TemporalEdge(
            edge=rec, valid_from=now - timedelta(days=5), valid_until=None
        )
        assert te.is_active_at(now) is True


# ---------------------------------------------------------------------------
# graph_runtime (unit)
# ---------------------------------------------------------------------------


class TestGraphRuntime:
    def test_components_instantiated(self):
        from app.graph.graph_runtime import GraphRuntime
        from app.graph.graph_queries import GraphQueryEngine
        from app.graph.graph_resolver import GraphResolver
        from app.graph.temporal_chain import TemporalChain

        mock_db = MagicMock()
        rt = GraphRuntime(mock_db)
        assert isinstance(rt.queries, GraphQueryEngine)
        assert isinstance(rt.resolver, GraphResolver)
        assert isinstance(rt.temporal, TemporalChain)

    def test_clear_registry(self):
        from app.graph.graph_runtime import GraphRuntime
        from app.graph.entity_registry import EntityRegistry

        mock_db = MagicMock()
        rt = GraphRuntime(mock_db)
        # Put something in cache then clear via runtime
        e = MagicMock()
        e.id = 777
        rt.registry.put(e)
        rt.clear_registry()
        assert rt.registry.size == 0
