"""Tests for the embeddings service and semantic retrieval integration.

All tests run with ``JTA_EMBEDDINGS_ENABLED=false`` (the default in the test
environment) so they are fast and do not require sentence-transformers or GPU.
The enabled=True code paths are exercised via monkeypatching.
"""

from __future__ import annotations

import datetime
import importlib
import os

import pytest

from app.db.session import SessionLocal
from app.models.entities import (
    CanonicalEntity,
    MemoryClaim,
    SourceRegistry,
    SourceSnapshot,
)
from app.memory import claim_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(db, key: str) -> SourceRegistry:
    reg = db.query(SourceRegistry).filter_by(source_key=key).first()
    if reg:
        return reg
    reg = SourceRegistry(
        source_key=key,
        source_name=key,
        source_tier="court_direct",
        is_active=True,
        requires_manual_review=False,
        auto_publish_enabled=False,
    )
    db.add(reg)
    db.flush()
    return reg


def _make_entity(db, name: str) -> CanonicalEntity:
    e = CanonicalEntity(
        entity_type="judge",
        canonical_name=name,
        confidence_score=0.9,
    )
    db.add(e)
    db.flush()
    return e


def _make_claim(
    db, entity, claim_type: str, claim_value: str, embedding=None
) -> MemoryClaim:
    payload = {
        "claim_type": claim_type,
        "subject_type": entity.entity_type,
        "subject_id": entity.id,
        "predicate": "test_predicate",
        "object_type": None,
        "object_id": None,
        "normalized_text": claim_value,
    }
    key = claim_key(payload)
    claim = MemoryClaim(  # type: ignore[call-arg]
        entity_id=entity.id,
        claim_key=key,
        claim_type=claim_type,
        claim_value=claim_value,
        confidence=0.8,
        is_active=True,
        status="active",
        claim_embedding=embedding,
    )
    db.add(claim)
    db.flush()
    return claim


# ---------------------------------------------------------------------------
# cosine_similarity (pure math, no DB needed)
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors():
    from app.services.embeddings import cosine_similarity

    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    from app.services.embeddings import cosine_similarity

    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    from app.services.embeddings import cosine_similarity

    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_raises_on_length_mismatch():
    from app.services.embeddings import cosine_similarity

    with pytest.raises(ValueError, match="length mismatch"):
        cosine_similarity([1.0, 2.0], [1.0])


# ---------------------------------------------------------------------------
# cosine_similarity_unnormed
# ---------------------------------------------------------------------------


def test_cosine_similarity_unnormed_same_direction():
    from app.services.embeddings import cosine_similarity_unnormed

    a = [3.0, 0.0]
    b = [7.0, 0.0]
    assert cosine_similarity_unnormed(a, b) == pytest.approx(1.0)


def test_cosine_similarity_unnormed_zero_vector_returns_zero():
    from app.services.embeddings import cosine_similarity_unnormed

    a = [0.0, 0.0]
    b = [1.0, 0.0]
    assert cosine_similarity_unnormed(a, b) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# encode() — disabled path (no sentence-transformers needed)
# ---------------------------------------------------------------------------


def test_encode_returns_none_when_embeddings_disabled():
    """encode() must short-circuit when embeddings_enabled=False (default in tests)."""
    from app.services.embeddings import encode

    result = encode("some text about a judge sentencing")
    assert result is None


def test_encode_returns_none_for_empty_string():
    """encode() must return None for blank/empty input even if model were loaded."""
    from app.services.embeddings import encode

    assert encode("") is None
    assert encode("   ") is None


# ---------------------------------------------------------------------------
# encode() — enabled path via monkeypatch
# ---------------------------------------------------------------------------


def test_encode_returns_float_list_when_enabled(monkeypatch):
    import app.services.embeddings as emb_mod

    # Fake model whose encode() returns a known vector
    class _FakeModel:
        def encode(self, text, normalize_embeddings=True):
            return [0.5, 0.5]

    # Force module to think embeddings are enabled and inject fake model
    monkeypatch.setattr(emb_mod, "_model", _FakeModel())
    monkeypatch.setattr(emb_mod, "_model_name", "all-MiniLM-L6-v2")

    # Patch get_settings to return embeddings_enabled=True
    class _FakeSettings:
        embeddings_enabled = True
        embeddings_model = "all-MiniLM-L6-v2"
        embeddings_similarity_threshold = 0.70
        embeddings_top_k = 5

    monkeypatch.setattr(emb_mod, "get_settings", lambda: _FakeSettings())

    result = emb_mod.encode("judge sentenced defendant")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# find_similar_claims() — disabled (no DB writes needed)
# ---------------------------------------------------------------------------


def test_find_similar_claims_returns_empty_when_disabled(db_session):
    from app.services.embeddings import find_similar_claims

    results = find_similar_claims("judge sentenced 5 years", db_session)
    assert results == []


# ---------------------------------------------------------------------------
# find_similar_claims() — enabled path using monkeypatched encode
# ---------------------------------------------------------------------------


def test_find_similar_claims_returns_claims_above_threshold(db_session, monkeypatch):
    import app.services.embeddings as emb_mod

    _make_source(db_session, "emb_sim_src")
    entity = _make_entity(db_session, "Embeddings Judge A")

    # High-similarity claim (dot product = 1.0 for unit vector [1, 0])
    high_claim = _make_claim(
        db_session, entity, "sentence_length", "5 years", embedding=[1.0, 0.0]
    )
    # Low-similarity claim (dot product = 0.0, orthogonal)
    _low_claim = _make_claim(
        db_session, entity, "bail_decision", "denied", embedding=[0.0, 1.0]
    )
    db_session.flush()

    # Monkeypatch encode() to return query vector [1, 0]
    monkeypatch.setattr(emb_mod, "encode", lambda text: [1.0, 0.0])

    class _FakeSettings:
        embeddings_enabled = True
        embeddings_model = "all-MiniLM-L6-v2"
        embeddings_similarity_threshold = 0.80  # only high_claim passes
        embeddings_top_k = 10

    monkeypatch.setattr(emb_mod, "get_settings", lambda: _FakeSettings())

    results = emb_mod.find_similar_claims(
        "sentenced 5 years", db_session, threshold=0.80
    )
    ids = [c.id for c in results]
    assert high_claim.id in ids


def test_find_similar_claims_excludes_below_threshold(db_session, monkeypatch):
    import app.services.embeddings as emb_mod

    _make_source(db_session, "emb_below_src")
    entity = _make_entity(db_session, "Embeddings Judge B")
    _low_claim = _make_claim(
        db_session, entity, "charge_type", "wire fraud", embedding=[0.0, 1.0]
    )
    db_session.flush()

    # Query vector orthogonal to stored vector → similarity = 0
    monkeypatch.setattr(emb_mod, "encode", lambda text: [1.0, 0.0])

    class _FakeSettings:
        embeddings_enabled = True
        embeddings_model = "all-MiniLM-L6-v2"
        embeddings_similarity_threshold = 0.70
        embeddings_top_k = 10

    monkeypatch.setattr(emb_mod, "get_settings", lambda: _FakeSettings())

    results = emb_mod.find_similar_claims("securities fraud", db_session)
    # Orthogonal vector should not pass 0.70 threshold
    assert results == []


# ---------------------------------------------------------------------------
# search_claims_semantic() via retrieval module
# ---------------------------------------------------------------------------


def test_search_claims_semantic_returns_empty_when_disabled(db_session):
    from app.memory.retrieval import search_claims_semantic

    results = search_claims_semantic("convicted of fraud", db_session)
    assert results == []


def test_search_claims_semantic_delegates_to_find_similar(db_session, monkeypatch):
    import app.services.embeddings as emb_mod
    from app.memory.retrieval import search_claims_semantic

    _make_source(db_session, "ret_sem_src")
    entity = _make_entity(db_session, "Retrieval Judge X")
    matching_claim = _make_claim(
        db_session, entity, "disposition", "convicted", embedding=[1.0, 0.0]
    )
    db_session.flush()

    monkeypatch.setattr(emb_mod, "encode", lambda text: [1.0, 0.0])

    class _FakeSettings:
        embeddings_enabled = True
        embeddings_model = "all-MiniLM-L6-v2"
        embeddings_similarity_threshold = 0.80
        embeddings_top_k = 10

    monkeypatch.setattr(emb_mod, "get_settings", lambda: _FakeSettings())

    results = search_claims_semantic(
        "judge convicted defendant", db_session, threshold=0.80
    )
    ids = [c.id for c in results]
    assert matching_claim.id in ids
