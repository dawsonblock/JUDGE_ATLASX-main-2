"""Tests for contradiction-priority deduplication and temporal as-of query.

Covers:
  - get_contradictions_for_claim_pair   — bidirectional fetch
  - select_canonical_contradiction      — severity / authority / recency ordering
  - dedupe_contradictions_for_entity    — demotes non-canonical open records
  - query_claims_as_of                  — point-in-time valid_from/valid_to filter
  - _check_temporal_contradiction       — overlap window detection (regression)
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.entities import (
    CanonicalEntity,
    MemoryClaim,
    MemoryContradiction,
)
from app.memory.contradiction_engine import (
    dedupe_contradictions_for_entity,
    get_contradictions_for_claim_pair,
    query_claims_as_of,
    select_canonical_contradiction,
    _check_temporal_contradiction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _entity(db_session):
    e = CanonicalEntity(entity_type="person", canonical_name=f"Test Entity {uuid4().hex[:6]}")
    db_session.add(e)
    db_session.flush()
    return e


def _claim(db_session, entity_id, *, predicate="role", value="A", valid_from=None, valid_to=None):
    c = MemoryClaim(
        claim_key=f"ck_{uuid4().hex[:12]}",
        claim_type="role",
        entity_id=entity_id,
        claim_value=value,
        normalized_value=value,
        object_value_type="text",
        predicate=predicate,
        confidence=0.8,
        contradiction_count=0,
        review_status="approved",
        status="active",
        is_active=True,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _contradiction(db_session, claim_a, claim_b, *, conflict_type="value_contradiction",
                   severity="medium", status="open", authority_weight=0.5,
                   detected_at=None):
    mc = MemoryContradiction(
        claim_a_id=claim_a.id,
        claim_b_id=claim_b.id,
        conflict_type=conflict_type,
        severity=severity,
        status=status,
        detected_by="test",
        detected_at=detected_at or _NOW,
        source_authority_weight=authority_weight,
    )
    db_session.add(mc)
    db_session.flush()
    return mc


# ---------------------------------------------------------------------------
# get_contradictions_for_claim_pair
# ---------------------------------------------------------------------------

class TestGetContradictionsForClaimPair:
    def test_returns_all_records_for_pair(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        mc1 = _contradiction(db_session, c1, c2, conflict_type="value_contradiction")
        mc2 = _contradiction(db_session, c1, c2, conflict_type="temporal_contradiction")
        db_session.commit()

        result = get_contradictions_for_claim_pair(c1.id, c2.id, db_session)
        ids = {r.id for r in result}
        assert mc1.id in ids
        assert mc2.id in ids

    def test_bidirectional_lookup(self, db_session):
        """Should find records regardless of which claim is A and which is B."""
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        mc = _contradiction(db_session, c1, c2)
        db_session.commit()

        # Query with reversed arg order.
        result = get_contradictions_for_claim_pair(c2.id, c1.id, db_session)
        assert any(r.id == mc.id for r in result)

    def test_no_false_cross_pair_matches(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        c3 = _claim(db_session, e.id)
        _contradiction(db_session, c1, c3)
        db_session.commit()

        # Pair (c1, c2) should return nothing.
        result = get_contradictions_for_claim_pair(c1.id, c2.id, db_session)
        assert result == []


# ---------------------------------------------------------------------------
# select_canonical_contradiction
# ---------------------------------------------------------------------------

class TestSelectCanonicalContradiction:
    def _mc(self, severity, weight, detected_at):
        return SimpleNamespace(
            id=id(object()),  # unique integer
            severity=severity,
            source_authority_weight=weight,
            detected_at=detected_at,
        )

    def test_empty_list_returns_none(self):
        assert select_canonical_contradiction([]) is None

    def test_single_item_returned(self):
        mc = self._mc("high", 0.5, _NOW)
        assert select_canonical_contradiction([mc]) is mc

    def test_severity_wins_over_recency(self):
        older_critical = self._mc("critical", 0.5, _NOW - timedelta(days=10))
        newer_low = self._mc("low", 0.9, _NOW)
        result = select_canonical_contradiction([newer_low, older_critical])
        assert result is older_critical

    def test_authority_breaks_severity_tie(self):
        hi_auth = self._mc("high", 0.9, _NOW)
        lo_auth = self._mc("high", 0.3, _NOW)
        result = select_canonical_contradiction([lo_auth, hi_auth])
        assert result is hi_auth

    def test_recency_breaks_authority_tie(self):
        older = self._mc("high", 0.7, _NOW - timedelta(seconds=30))
        newer = self._mc("high", 0.7, _NOW)
        result = select_canonical_contradiction([older, newer])
        assert result is newer

    def test_all_severities_ranked_correctly(self):
        low = self._mc("low", 1.0, _NOW)
        medium = self._mc("medium", 1.0, _NOW)
        high = self._mc("high", 1.0, _NOW)
        critical = self._mc("critical", 1.0, _NOW)
        result = select_canonical_contradiction([low, high, medium, critical])
        assert result is critical


# ---------------------------------------------------------------------------
# dedupe_contradictions_for_entity
# ---------------------------------------------------------------------------

class TestDedupeContradictionsForEntity:
    def test_no_claims_returns_zero(self, db_session):
        result = dedupe_contradictions_for_entity(9999999, db_session)
        assert result == 0

    def test_single_contradiction_per_pair_not_demoted(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        _contradiction(db_session, c1, c2, severity="medium")
        db_session.commit()

        count = dedupe_contradictions_for_entity(e.id, db_session)
        assert count == 0

    def test_demotes_lower_priority_duplicates(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        # Two records for same pair: one critical, one low.
        mc_critical = _contradiction(db_session, c1, c2, conflict_type="value_contradiction",
                                     severity="critical", authority_weight=0.8)
        mc_low = _contradiction(db_session, c1, c2, conflict_type="temporal_contradiction",
                                severity="low", authority_weight=0.2)
        db_session.commit()

        count = dedupe_contradictions_for_entity(e.id, db_session)
        assert count == 1

        db_session.refresh(mc_critical)
        db_session.refresh(mc_low)
        assert mc_critical.status == "open"
        assert mc_low.status == "false_positive"
        assert f"superseded_by_canonical:{mc_critical.id}" in (mc_low.resolution_note or "")

    def test_already_resolved_records_not_touched(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        mc_high = _contradiction(db_session, c1, c2, conflict_type="value_contradiction",
                                 severity="high")
        mc_resolved = _contradiction(db_session, c1, c2, conflict_type="temporal_contradiction",
                                     severity="low", status="resolved")
        db_session.commit()

        count = dedupe_contradictions_for_entity(e.id, db_session)
        # mc_resolved is already closed — only the non-canonical open records count.
        db_session.refresh(mc_resolved)
        assert mc_resolved.status == "resolved"  # untouched
        # mc_high is the only open record → nothing to demote.
        assert count == 0

    def test_multiple_pairs_each_deduped_independently(self, db_session):
        e = _entity(db_session)
        c1 = _claim(db_session, e.id)
        c2 = _claim(db_session, e.id)
        c3 = _claim(db_session, e.id)
        # Pair (c1, c2): two open records.
        _contradiction(db_session, c1, c2, conflict_type="value_contradiction", severity="high")
        _contradiction(db_session, c1, c2, conflict_type="temporal_contradiction", severity="low")
        # Pair (c1, c3): one open record — nothing to demote.
        _contradiction(db_session, c1, c3, severity="medium")
        db_session.commit()

        count = dedupe_contradictions_for_entity(e.id, db_session)
        assert count == 1  # Only the (c1,c2) low-priority record demoted.


# ---------------------------------------------------------------------------
# query_claims_as_of
# ---------------------------------------------------------------------------

class TestQueryClaimsAsOf:
    def test_returns_open_ended_claims(self, db_session):
        """Claims with no valid_from/valid_to are always valid."""
        e = _entity(db_session)
        c = _claim(db_session, e.id, value="Judge", valid_from=None, valid_to=None)
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session)
        assert any(r.id == c.id for r in result)

    def test_excludes_future_claim(self, db_session):
        """Claim with valid_from after as_of should not appear."""
        e = _entity(db_session)
        future = _NOW + timedelta(days=30)
        c = _claim(db_session, e.id, value="Future", valid_from=future)
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session)
        assert not any(r.id == c.id for r in result)

    def test_excludes_expired_claim(self, db_session):
        """Claim with valid_to at or before as_of should not appear."""
        e = _entity(db_session)
        past_start = _NOW - timedelta(days=60)
        past_end = _NOW - timedelta(days=1)
        c = _claim(db_session, e.id, value="Expired", valid_from=past_start, valid_to=past_end)
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session)
        assert not any(r.id == c.id for r in result)

    def test_includes_active_bounded_claim(self, db_session):
        """Claim where valid_from <= as_of < valid_to should be included."""
        e = _entity(db_session)
        start = _NOW - timedelta(days=10)
        end = _NOW + timedelta(days=10)
        c = _claim(db_session, e.id, value="Active", valid_from=start, valid_to=end)
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session)
        assert any(r.id == c.id for r in result)

    def test_predicate_filter(self, db_session):
        e = _entity(db_session)
        c_role = _claim(db_session, e.id, predicate="role", value="Judge")
        c_status = _claim(db_session, e.id, predicate="case_status", value="active")
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session, predicate="role")
        result_ids = {r.id for r in result}
        assert c_role.id in result_ids
        assert c_status.id not in result_ids

    def test_excludes_inactive_claims(self, db_session):
        e = _entity(db_session)
        c = _claim(db_session, e.id, value="Inactive")
        c.is_active = False
        c.status = "superseded"
        db_session.commit()

        result = query_claims_as_of(e.id, _NOW, db_session)
        assert not any(r.id == c.id for r in result)

    def test_unknown_entity_returns_empty(self, db_session):
        result = query_claims_as_of(9999999, _NOW, db_session)
        assert result == []


# ---------------------------------------------------------------------------
# _check_temporal_contradiction — overlap window regression tests
# ---------------------------------------------------------------------------

class TestCheckTemporalContradictionOverlap:
    """Unit-level tests for the improved overlap window detection."""

    def _minimal_claim(self, cid, value, valid_from, valid_to=None):
        return SimpleNamespace(
            id=cid,
            normalized_value=value,
            valid_from=valid_from,
            valid_to=valid_to,
            predicate="case_status",
            confidence=0.8,
            object_value_type="text",
            source_snapshot_id=None,
            entity_id=1,
        )

    def test_same_open_window_different_values_is_contradiction(self, db_session):
        start = _NOW - timedelta(days=5)
        c1 = self._minimal_claim(1, "convicted", start)
        c2 = self._minimal_claim(2, "acquitted", start)
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is not None
        assert result["type"] == "temporal_contradiction"

    def test_non_overlapping_windows_not_contradiction(self, db_session):
        c1 = self._minimal_claim(1, "convicted",
                                  _NOW - timedelta(days=20),
                                  _NOW - timedelta(days=10))
        c2 = self._minimal_claim(2, "acquitted",
                                  _NOW - timedelta(days=5))
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is None

    def test_overlapping_windows_different_values_is_contradiction(self, db_session):
        c1 = self._minimal_claim(1, "convicted",
                                  _NOW - timedelta(days=10),
                                  _NOW + timedelta(days=10))
        c2 = self._minimal_claim(2, "acquitted",
                                  _NOW - timedelta(days=5),
                                  _NOW + timedelta(days=20))
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is not None

    def test_overlapping_windows_same_values_not_contradiction(self, db_session):
        c1 = self._minimal_claim(1, "convicted",
                                  _NOW - timedelta(days=10))
        c2 = self._minimal_claim(2, "convicted",
                                  _NOW - timedelta(days=5))
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is None

    def test_missing_valid_from_skipped(self, db_session):
        c1 = self._minimal_claim(1, "convicted", None)
        c2 = self._minimal_claim(2, "acquitted", _NOW)
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is None

    def test_abutting_windows_not_contradiction(self, db_session):
        """valid_to of first == valid_from of second — no actual overlap."""
        boundary = _NOW
        c1 = self._minimal_claim(1, "convicted",
                                  boundary - timedelta(days=10), boundary)
        c2 = self._minimal_claim(2, "acquitted", boundary)
        result = _check_temporal_contradiction(c1, c2, db_session)
        assert result is None
