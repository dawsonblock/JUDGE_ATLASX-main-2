"""Tests for memory invalidation helpers in app.memory.invalidation."""

import pytest
from unittest.mock import MagicMock

from app.memory.invalidation import invalidate_claim, invalidate_entity_state
from app.models.entities import MemoryClaim, MemoryEntityState, MemoryInvalidation


class TestInvalidateClaim:
    def _mock_db_with_claim(self, claim):
        db = MagicMock()
        db.get.return_value = claim
        return db

    def test_marks_claim_inactive(self):
        claim = MagicMock(spec=MemoryClaim)
        claim.is_active = True
        db = self._mock_db_with_claim(claim)
        invalidate_claim(1, "test reason", db)
        assert claim.is_active is False

    def test_writes_audit_record(self):
        claim = MagicMock(spec=MemoryClaim)
        claim.id = 1
        db = self._mock_db_with_claim(claim)
        result = invalidate_claim(1, "test reason", db)
        db.add.assert_called_once()
        assert isinstance(result, MemoryInvalidation)

    def test_raises_for_missing_claim(self):
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(ValueError, match="does not exist"):
            invalidate_claim(99, "reason", db)

    def test_audit_records_rebuild_run_id(self):
        claim = MagicMock(spec=MemoryClaim)
        claim.id = 5
        db = self._mock_db_with_claim(claim)
        result = invalidate_claim(5, "purge", db, rebuild_run_id=42)
        assert result.triggered_by_rebuild_run_id == 42

    def test_audit_reason_stored(self):
        claim = MagicMock(spec=MemoryClaim)
        claim.id = 3
        db = self._mock_db_with_claim(claim)
        result = invalidate_claim(3, "my reason", db)
        assert result.reason == "my reason"


class TestInvalidateEntityState:
    def test_raises_when_no_state(self):
        db = MagicMock()
        # query() chain returns no entity state
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        with pytest.raises(ValueError, match="No MemoryEntityState for entity"):
            invalidate_entity_state(123, "reason", db)

    def test_invalidates_all_active_claims(self):
        db = MagicMock()

        state = MagicMock(spec=MemoryEntityState)
        state.active_claim_count = 2

        claim_a = MagicMock(spec=MemoryClaim)
        claim_a.id = 10
        claim_a.is_active = True
        claim_b = MagicMock(spec=MemoryClaim)
        claim_b.id = 11
        claim_b.is_active = True

        q_state = MagicMock()
        q_state.filter.return_value.first.return_value = state

        q_claims = MagicMock()
        q_claims.filter.return_value.filter.return_value.all.return_value = [
            claim_a,
            claim_b,
        ]

        db.query.side_effect = [q_state, q_claims]

        invalidate_entity_state(1, "full rebuild", db)

        assert claim_a.is_active is False
        assert claim_b.is_active is False
        assert state.active_claim_count == 0

    def test_adds_audit_record_for_each_invalidated_claim(self):
        db = MagicMock()

        state = MagicMock(spec=MemoryEntityState)
        state.active_claim_count = 1

        claim = MagicMock(spec=MemoryClaim)
        claim.id = 7
        claim.is_active = True

        q_state = MagicMock()
        q_state.filter.return_value.first.return_value = state

        q_claims = MagicMock()
        q_claims.filter.return_value.filter.return_value.all.return_value = [claim]

        db.query.side_effect = [q_state, q_claims]

        invalidate_entity_state(1, "test", db, rebuild_run_id=5)

        # db.add should be called at least once for the audit record
        db.add.assert_called()
