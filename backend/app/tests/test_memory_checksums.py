"""Tests for memory checksum helpers in app.memory."""

from app.memory import (
    claim_key,
    entity_summary_checksum,
    evidence_checksum,
    stable_json_hash,
    state_checksum,
)


class TestStableJsonHash:
    def test_deterministic(self):
        assert stable_json_hash({"a": 1}) == stable_json_hash({"a": 1})

    def test_key_order_independent(self):
        assert stable_json_hash({"b": 2, "a": 1}) == stable_json_hash({"a": 1, "b": 2})

    def test_different_values_differ(self):
        assert stable_json_hash({"a": 1}) != stable_json_hash({"a": 2})

    def test_returns_64_char_hex_string(self):
        result = stable_json_hash("test")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_nested_structures(self):
        a = stable_json_hash({"outer": {"inner": [1, 2, 3]}})
        b = stable_json_hash({"outer": {"inner": [1, 2, 3]}})
        assert a == b


class TestClaimKey:
    def _payload(self, **overrides) -> dict:
        base = {
            "claim_type": "role",
            "subject_type": "judge",
            "subject_id": 42,
            "predicate": "has_role",
            "object_type": None,
            "object_id": None,
            "normalized_text": "District Judge",
        }
        base.update(overrides)
        return base

    def test_deterministic(self):
        assert claim_key(self._payload()) == claim_key(self._payload())

    def test_whitespace_stripped_from_normalized_text(self):
        a = claim_key(self._payload(normalized_text="District Judge"))
        b = claim_key(self._payload(normalized_text="  district judge  "))
        assert a == b

    def test_different_subject_ids_produce_different_keys(self):
        a = claim_key(self._payload(subject_id=1))
        b = claim_key(self._payload(subject_id=2))
        assert a != b

    def test_different_predicates_produce_different_keys(self):
        a = claim_key(self._payload(predicate="has_role"))
        b = claim_key(self._payload(predicate="mentioned_in"))
        assert a != b

    def test_returns_64_char_hex(self):
        assert len(claim_key(self._payload())) == 64


class TestEvidenceChecksum:
    def test_order_independent(self):
        items = [{"text": "alpha"}, {"text": "beta"}]
        assert evidence_checksum(items) == evidence_checksum(list(reversed(items)))

    def test_different_items_differ(self):
        assert evidence_checksum([{"x": 1}]) != evidence_checksum([{"x": 2}])

    def test_empty_list_returns_64_char_hex(self):
        result = evidence_checksum([])
        assert isinstance(result, str)
        assert len(result) == 64

    def test_single_item_deterministic(self):
        item = [{"url": "https://example.com", "hash": "abc123"}]
        assert evidence_checksum(item) == evidence_checksum(item)


class TestEntitySummaryChecksum:
    def test_deterministic(self):
        claims = [{"claim_key": "abc", "claim_type": "role"}]
        assert entity_summary_checksum(claims) == entity_summary_checksum(claims)

    def test_order_independent(self):
        c1 = {"claim_key": "aaa", "claim_type": "role"}
        c2 = {"claim_key": "bbb", "claim_type": "name_mention"}
        assert entity_summary_checksum([c1, c2]) == entity_summary_checksum([c2, c1])

    def test_additional_claim_changes_checksum(self):
        c1 = {"claim_key": "aaa", "claim_type": "role"}
        c2 = {"claim_key": "bbb", "claim_type": "role"}
        assert entity_summary_checksum([c1]) != entity_summary_checksum([c1, c2])

    def test_empty_claims(self):
        result = entity_summary_checksum([])
        assert isinstance(result, str)
        assert len(result) == 64


class TestStateChecksum:
    def test_deterministic(self):
        s = {"display_name": "Alice", "roles": ["judge"], "count": 3}
        assert state_checksum(s) == state_checksum(s)

    def test_different_state_differs(self):
        assert state_checksum({"a": 1}) != state_checksum({"a": 2})

    def test_returns_64_char_hex(self):
        assert len(state_checksum({})) == 64
