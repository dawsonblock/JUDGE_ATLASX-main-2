"""Tests for graph central layer (Phase 8).

Tests entity resolution, claim mapping, and entity state rebuilds.
"""

import pytest

from app.models.entities import CanonicalEntity, MemoryClaim, MemoryEntityState
from app.graph.graph_central import (
    resolve_entity_from_claim,
    rebuild_entity_state,
    batch_rebuild_entity_states,
    get_entity_graph,
)


class TestEntityResolution:
    """Test entity resolution from claims."""

    def test_resolve_entity_from_claim_with_entity_id(self, db_session):
        """Test resolving entity when claim has entity_id."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        resolved = resolve_entity_from_claim(claim, db_session)
        assert resolved.id == entity.id
        assert resolved.canonical_name == "John Doe"

    def test_resolve_entity_fails_for_missing_entity(self, db_session):
        """Test that resolution fails for missing entity."""
        claim = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="test",
            entity_id=999999,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        with pytest.raises(ValueError):
            resolve_entity_from_claim(claim, db_session)


class TestEntityStateRebuild:
    """Test entity state rebuild functionality."""

    def test_rebuild_entity_state(self, db_session):
        """Test rebuilding entity state from claims."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        db_session.add(entity)
        db_session.commit()

        # Add claims
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="alias",
            entity_id=entity.id,
            claim_value="Johnny",
            normalized_value="Johnny",
            is_active=True,
            status="active",
        )
        claim2 = MemoryClaim(
            claim_key="test_claim_2",
            claim_type="role",
            entity_id=entity.id,
            claim_value="Judge",
            normalized_value="Judge",
            is_active=True,
            status="active",
        )
        db_session.add_all([claim1, claim2])
        db_session.commit()

        entity_state = rebuild_entity_state(entity.id, db_session)

        assert entity_state.entity_id == entity.id
        assert entity_state.display_name == "John Doe"
        assert "Johnny" in entity_state.aliases
        assert "Judge" in entity_state.roles
        assert entity_state.state_checksum is not None

    def test_rebuild_nonexistent_entity_fails(self, db_session):
        """Test that rebuilding nonexistent entity fails."""
        with pytest.raises(ValueError):
            rebuild_entity_state(999999, db_session)

    def test_batch_rebuild_entity_states(self, db_session):
        """Test batch rebuild of entity states."""
        entity1 = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        entity2 = CanonicalEntity(
            entity_type="person",
            canonical_name="Jane Smith",
        )
        db_session.add_all([entity1, entity2])
        db_session.commit()

        # Add claims
        claim1 = MemoryClaim(
            claim_key="test_claim_1",
            claim_type="alias",
            entity_id=entity1.id,
            claim_value="Johnny",
            normalized_value="Johnny",
            is_active=True,
            status="active",
        )
        db_session.add(claim1)
        db_session.commit()

        rebuilt_count = batch_rebuild_entity_states(db_session)
        assert rebuilt_count >= 2


class TestEntityGraph:
    """Test entity graph representation."""

    def test_get_entity_graph(self, db_session):
        """Test getting graph representation of entity."""
        entity = CanonicalEntity(
            entity_type="person",
            canonical_name="John Doe",
        )
        db_session.add(entity)
        db_session.commit()

        graph = get_entity_graph(entity.id, db_session)

        assert "entity" in graph
        assert graph["entity"]["id"] == entity.id
        assert graph["entity"]["canonical_name"] == "John Doe"
        assert "outgoing_edges" in graph
        assert "incoming_edges" in graph

    def test_get_graph_nonexistent_entity_fails(self, db_session):
        """Test that getting graph for nonexistent entity fails."""
        with pytest.raises(ValueError):
            get_entity_graph(999999, db_session)

