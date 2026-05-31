"""Tests for derivative-boundary invariants in the memory subsystem.

Covers three areas:
  A. extract_claims — what may be derived from snapshot text, and what must not
  B. _HARD_REASONS — the frozenset that protects hard-rejected claims from re-activation
  C. retrieval helpers — boundary conditions on list_claims / search_claims_semantic
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.memory.extract_claims import extract_claims
from app.memory.rebuild import _HARD_REASONS
from app.memory.retrieval import list_claims, search_claims_semantic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entity(
    entity_id: int = 1,
    canonical_name: str = "Jane Doe",
    entity_type: str = "person",
) -> SimpleNamespace:
    """Minimal stand-in for CanonicalEntity."""
    return SimpleNamespace(id=entity_id, canonical_name=canonical_name, entity_type=entity_type)


def _make_snapshot(extracted_text: str | None = None, raw_content: str | None = None) -> SimpleNamespace:
    """Minimal stand-in for SourceSnapshot."""
    return SimpleNamespace(extracted_text=extracted_text, raw_content=raw_content)


# ---------------------------------------------------------------------------
# Group A — extract_claims derivation boundaries
# ---------------------------------------------------------------------------

class TestExtractClaimsDerivationBoundaries:

    def test_no_claims_when_both_text_fields_are_empty_string(self):
        snapshot = _make_snapshot(extracted_text="", raw_content="")
        entity = _make_entity()
        result = extract_claims(snapshot, entity, MagicMock())
        assert result == []

    def test_no_claims_when_both_text_fields_are_none(self):
        snapshot = _make_snapshot(extracted_text=None, raw_content=None)
        entity = _make_entity()
        result = extract_claims(snapshot, entity, MagicMock())
        assert result == []

    def test_raw_content_used_when_extracted_text_is_none(self):
        entity = _make_entity(canonical_name="Acme Corp", entity_type="organization")
        snapshot = _make_snapshot(extracted_text=None, raw_content="Acme Corp is a company.")
        result = extract_claims(snapshot, entity, MagicMock())
        types = [c["claim_type"] for c in result]
        assert "entity_type" in types

    def test_entity_type_claim_emitted_for_any_non_empty_text(self):
        entity = _make_entity()
        snapshot = _make_snapshot(extracted_text="Some unrelated text about nobody.")
        result = extract_claims(snapshot, entity, MagicMock())
        assert any(c["claim_type"] == "entity_type" for c in result)

    def test_entity_type_claim_value_equals_entity_type_field(self):
        entity = _make_entity(entity_type="organization")
        snapshot = _make_snapshot(extracted_text="Placeholder text for the org.")
        result = extract_claims(snapshot, entity, MagicMock())
        et_claims = [c for c in result if c["claim_type"] == "entity_type"]
        assert et_claims, "entity_type claim must be present"
        assert et_claims[0]["claim_value"] == "organization"

    def test_no_name_mention_when_entity_name_absent_from_text(self):
        entity = _make_entity(canonical_name="Jane Doe")
        snapshot = _make_snapshot(extracted_text="John Smith appeared in court today.")
        result = extract_claims(snapshot, entity, MagicMock())
        assert not any(c["claim_type"] == "name_mention" for c in result)

    def test_name_mention_emitted_when_name_present_in_text(self):
        entity = _make_entity(canonical_name="Jane Doe")
        snapshot = _make_snapshot(extracted_text="Jane Doe was arraigned this morning.")
        result = extract_claims(snapshot, entity, MagicMock())
        assert any(c["claim_type"] == "name_mention" for c in result)

    def test_role_claim_extracted_when_keyword_within_300_char_window(self):
        entity = _make_entity(canonical_name="Robert Burns")
        # Entity name + role keyword inside 300-char window.
        text = "Robert Burns, a district judge, presided over the hearing."
        snapshot = _make_snapshot(extracted_text=text)
        result = extract_claims(snapshot, entity, MagicMock())
        assert any(c["claim_type"] == "role" for c in result)

    def test_role_claim_not_extracted_when_keyword_beyond_300_char_window(self):
        entity = _make_entity(canonical_name="Robert Burns")
        # 400 chars of filler then role keyword — beyond ±300 window.
        filler = "x" * 400
        text = f"Robert Burns {filler} district judge presided."
        snapshot = _make_snapshot(extracted_text=text)
        result = extract_claims(snapshot, entity, MagicMock())
        assert not any(c["claim_type"] == "role" for c in result)

    def test_all_emitted_claims_are_bound_to_entity_id(self):
        entity = _make_entity(entity_id=42, canonical_name="Alice Brown")
        text = "Alice Brown, a magistrate judge, was sentenced to probation."
        snapshot = _make_snapshot(extracted_text=text)
        result = extract_claims(snapshot, entity, MagicMock())
        assert result, "expected at least one claim"
        for claim in result:
            assert claim["entity_id"] == 42, (
                f"claim {claim['claim_type']} has entity_id {claim['entity_id']}, expected 42"
            )

    def test_no_role_claim_when_no_name_match_and_keyword_absent(self):
        entity = _make_entity(canonical_name="Nobody Special")
        snapshot = _make_snapshot(extracted_text="The weather was fine yesterday.")
        result = extract_claims(snapshot, entity, MagicMock())
        assert not any(c["claim_type"] == "role" for c in result)

    def test_bail_decision_claim_extracted_when_present(self):
        entity = _make_entity(canonical_name="Sam Green")
        text = "Sam Green bail was denied by the magistrate."
        snapshot = _make_snapshot(extracted_text=text)
        result = extract_claims(snapshot, entity, MagicMock())
        assert any(c["claim_type"] == "bail_decision" for c in result)

    def test_disposition_claim_extracted_when_present(self):
        entity = _make_entity(canonical_name="Alex Lee")
        text = "Alex Lee was convicted of wire fraud on Thursday."
        snapshot = _make_snapshot(extracted_text=text)
        result = extract_claims(snapshot, entity, MagicMock())
        assert any(c["claim_type"] == "disposition" for c in result)


# ---------------------------------------------------------------------------
# Group B — _HARD_REASONS frozenset protection
# ---------------------------------------------------------------------------

class TestHardReasonsBoundary:

    def test_hard_reasons_is_frozenset(self):
        assert isinstance(_HARD_REASONS, frozenset), (
            "_HARD_REASONS must be a frozenset to guarantee immutability"
        )

    def test_manual_reject_is_a_hard_reason(self):
        assert "manual_reject" in _HARD_REASONS

    def test_source_rejected_is_a_hard_reason(self):
        assert "source_rejected" in _HARD_REASONS

    def test_privacy_violation_is_a_hard_reason(self):
        assert "privacy_violation" in _HARD_REASONS

    def test_stale_rebuild_is_not_a_hard_reason(self):
        assert "stale_rebuild" not in _HARD_REASONS

    def test_empty_string_is_not_a_hard_reason(self):
        assert "" not in _HARD_REASONS

    def test_none_is_not_a_hard_reason(self):
        assert None not in _HARD_REASONS

    def test_hard_reasons_cannot_be_mutated(self):
        with pytest.raises((TypeError, AttributeError)):
            _HARD_REASONS.add("new_reason")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Group C — retrieval boundary conditions
# ---------------------------------------------------------------------------

class TestRetrievalBoundary:

    # -- list_claims --

    def test_list_claims_returns_empty_list_for_unknown_entity(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        db.query.return_value = q
        result = list_claims(db, entity_id=99999)
        assert result == []

    def test_list_claims_passes_entity_id_filter_to_query(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        db.query.return_value = q
        list_claims(db, entity_id=7)
        # filter() must have been called at least once (entity_id filter)
        q.filter.assert_called()

    def test_list_claims_no_filters_returns_all_from_db(self):
        fake_claims = [MagicMock(), MagicMock()]
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = fake_claims
        db.query.return_value = q
        result = list_claims(db)
        assert result is fake_claims

    # -- search_claims_semantic --

    def test_search_claims_semantic_returns_empty_when_embeddings_disabled(self):
        # find_similar_claims is lazily imported inside the function; patch the source.
        with patch(
            "app.services.embeddings.find_similar_claims",
            return_value=[],
        ):
            result = search_claims_semantic("any query text", MagicMock())
        assert result == []

    def test_search_claims_semantic_forwards_results_from_embeddings(self):
        fake = [MagicMock()]
        with patch(
            "app.services.embeddings.find_similar_claims",
            return_value=fake,
        ):
            result = search_claims_semantic("query", MagicMock(), k=3, threshold=0.7)
        assert result is fake
