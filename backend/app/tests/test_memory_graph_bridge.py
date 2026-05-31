"""Tests for memory_graph_bridge.sync_claims_to_graph.

Verifies that:
- Each mapped claim type produces exactly one EntityGraphEdge.
- Unknown claim types are silently skipped (0 edges inserted).
- A second call with identical claims inserts 0 new edges (idempotency).
- An empty claim list returns 0.
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.memory.memory_graph_bridge import sync_claims_to_graph
from app.models.entities import CanonicalEntity, EntityGraphEdge, MemoryClaim


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _make_entity(db) -> CanonicalEntity:
    entity = CanonicalEntity(
        entity_type="judge",
        canonical_name=f"Bridge Test Judge {_uid()}",
        canonical_id_external=f"bridge-judge-{_uid()}",
        merge_confidence=1.0,
        status="active",
    )
    db.add(entity)
    db.flush()
    return entity


def _make_claim(db, entity_id: int, claim_type: str) -> MemoryClaim:
    claim = MemoryClaim(
        claim_type=claim_type,
        entity_id=entity_id,
        claim_value="test value",
        confidence=0.9,
        is_active=True,
        status="active",
    )
    db.add(claim)
    db.flush()
    return claim


class TestMemoryGraphBridge:
    """Unit tests for sync_claims_to_graph."""

    def test_known_claim_types_produce_edges(self) -> None:
        """Every mapped claim type creates exactly one EntityGraphEdge."""
        known_types = ["name_mention", "role", "location", "affiliation", "title"]
        with SessionLocal() as db:
            entity = _make_entity(db)
            claims = [_make_claim(db, entity.id, ct) for ct in known_types]
            inserted = sync_claims_to_graph(entity.id, claims, db)
            db.flush()

            edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                )
                .all()
            )
            assert inserted == len(known_types)
            assert len(edges) == len(known_types)
            predicates = {e.predicate for e in edges}
            assert predicates == {
                "has_alias",
                "has_role",
                "located_in",
                "affiliated_with",
                "holds_title",
            }

    def test_unknown_claim_type_is_skipped(self) -> None:
        """Unknown claim types produce no edges and the function returns 0."""
        with SessionLocal() as db:
            entity = _make_entity(db)
            claim = _make_claim(db, entity.id, "unknown_type_xyz")
            inserted = sync_claims_to_graph(entity.id, [claim], db)
            assert inserted == 0

    def test_idempotent_second_call(self) -> None:
        """A second call with the same claims inserts 0 new edges."""
        with SessionLocal() as db:
            entity = _make_entity(db)
            claim = _make_claim(db, entity.id, "role")

            first = sync_claims_to_graph(entity.id, [claim], db)
            second = sync_claims_to_graph(entity.id, [claim], db)
            db.flush()

            assert first == 1
            assert second == 0
            edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                    EntityGraphEdge.predicate == "has_role",
                )
                .all()
            )
            assert len(edges) == 1

    def test_empty_claims_returns_zero(self) -> None:
        """An empty claim list inserts nothing and returns 0."""
        with SessionLocal() as db:
            entity = _make_entity(db)
            inserted = sync_claims_to_graph(entity.id, [], db)
            assert inserted == 0


class TestMemoryGraphBridgeInvalidation:
    """Graph invalidation and staleness edge-cases for sync_claims_to_graph."""

    def test_inactive_claim_is_skipped(self) -> None:
        """A claim with is_active=False must not produce an edge.

        The bridge guards defensively against inactive claims even if the
        caller is supposed to pre-filter.  Ensures stale claims left in a
        list never silently pollute the graph.
        """
        with SessionLocal() as db:
            entity = _make_entity(db)
            claim = _make_claim(db, entity.id, "role")
            claim.is_active = False
            db.flush()

            inserted = sync_claims_to_graph(entity.id, [claim], db)
            db.flush()

            assert inserted == 0
            edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                )
                .all()
            )
            assert edges == []

    def test_mixed_known_and_unknown_types_count(self) -> None:
        """Only mapped claim types contribute to the returned count."""
        with SessionLocal() as db:
            entity = _make_entity(db)
            known1 = _make_claim(db, entity.id, "name_mention")
            known2 = _make_claim(db, entity.id, "affiliation")
            unknown1 = _make_claim(db, entity.id, "unmapped_alpha")
            unknown2 = _make_claim(db, entity.id, "unmapped_beta")

            inserted = sync_claims_to_graph(
                entity.id, [known1, known2, unknown1, unknown2], db
            )
            db.flush()

            assert inserted == 2
            edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                )
                .all()
            )
            assert len(edges) == 2
            predicates = {e.predicate for e in edges}
            assert predicates == {"has_alias", "affiliated_with"}

    def test_incremental_second_batch_inserts_only_new(self) -> None:
        """Second call with a superset of claims inserts only genuinely new ones."""
        with SessionLocal() as db:
            entity = _make_entity(db)
            claim_a = _make_claim(db, entity.id, "role")
            claim_b = _make_claim(db, entity.id, "location")

            first = sync_claims_to_graph(entity.id, [claim_a], db)
            assert first == 1

            # Second call passes the original claim plus a new one.
            claim_c = _make_claim(db, entity.id, "title")
            second = sync_claims_to_graph(entity.id, [claim_a, claim_b, claim_c], db)
            db.flush()

            # Only claim_b and claim_c are new; claim_a is already persisted.
            assert second == 2
            total_edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                )
                .count()
            )
            assert total_edges == 3

    def test_nonexistent_entity_empty_claims_returns_zero(self) -> None:
        """Passing a non-existent entity id with no claims is safe and returns 0."""
        with SessionLocal() as db:
            inserted = sync_claims_to_graph(-99999, [], db)
            assert inserted == 0

    def test_all_predicate_mappings_are_correct(self) -> None:
        """Verify the hard-coded claim_type → predicate mapping for all 5 types."""
        expected = {
            "name_mention": "has_alias",
            "role": "has_role",
            "location": "located_in",
            "affiliation": "affiliated_with",
            "title": "holds_title",
        }
        with SessionLocal() as db:
            entity = _make_entity(db)
            claims = [_make_claim(db, entity.id, ct) for ct in expected]
            sync_claims_to_graph(entity.id, claims, db)
            db.flush()

            edges = (
                db.query(EntityGraphEdge)
                .filter(
                    EntityGraphEdge.subject_type == "canonical_entity",
                    EntityGraphEdge.subject_id == entity.id,
                )
                .all()
            )
            edge_map = {e.predicate for e in edges}
            assert edge_map == set(expected.values())
