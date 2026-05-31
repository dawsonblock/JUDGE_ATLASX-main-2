"""Tests for Phase B: Source trust tier formalization.

Covers:
- numeric_trust_tier() ordering
- compute_reliability_score() values
- SourceTierConflict model can be created and queried
- resolve_conflict() logic
- detect_conflicts() returns empty list for unknown source
- record_conflict() persists to DB with correct fields
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.conflict_resolution import (
    detect_conflicts,
    record_conflict,
    resolve_conflict,
)
from app.services.publish_rules import (
    TRUST_TIER_AGGREGATED_MEDIA,
    TRUST_TIER_POLICE_OPEN_DATA,
    TRUST_TIER_PRIMARY_OFFICIAL,
    TRUST_TIER_UNVERIFIED,
    TRUST_TIER_VERIFIED_NEWS,
    compute_reliability_score,
    numeric_trust_tier,
)

# ---------------------------------------------------------------------------
# numeric_trust_tier ordering
# ---------------------------------------------------------------------------


def test_court_record_has_max_tier():
    assert numeric_trust_tier("court_record") == TRUST_TIER_PRIMARY_OFFICIAL


def test_official_government_statistics_has_max_tier():
    assert (
        numeric_trust_tier("official_government_statistics")
        == TRUST_TIER_PRIMARY_OFFICIAL
    )


def test_official_police_open_data_tier():
    assert (
        numeric_trust_tier("official_police_open_data") == TRUST_TIER_POLICE_OPEN_DATA
    )


def test_verified_news_tier():
    assert numeric_trust_tier("verified_news_context") == TRUST_TIER_VERIFIED_NEWS


def test_news_rss_tier():
    assert numeric_trust_tier("news_rss") == TRUST_TIER_AGGREGATED_MEDIA


def test_news_only_context_tier():
    assert numeric_trust_tier("news_only_context") == TRUST_TIER_AGGREGATED_MEDIA


def test_media_cloud_tier():
    assert numeric_trust_tier("media_cloud") == TRUST_TIER_AGGREGATED_MEDIA


def test_scraped_media_tier():
    assert numeric_trust_tier("scraped_media") == TRUST_TIER_UNVERIFIED


def test_social_media_tier():
    assert numeric_trust_tier("social_media") == TRUST_TIER_UNVERIFIED


def test_unknown_tier_defaults_to_unverified():
    assert numeric_trust_tier("completely_unknown_source") == TRUST_TIER_UNVERIFIED


def test_tier_ordering_is_strict():
    """Verify the cardinal order court_record > police > news > media > unverified."""
    assert (
        numeric_trust_tier("court_record")
        > numeric_trust_tier("official_police_open_data")
        > numeric_trust_tier("verified_news_context")
        > numeric_trust_tier("news_rss")
        > numeric_trust_tier("scraped_media")
    )


def test_trust_tier_constants_ordering():
    assert (
        TRUST_TIER_PRIMARY_OFFICIAL
        > TRUST_TIER_POLICE_OPEN_DATA
        > TRUST_TIER_VERIFIED_NEWS
        > TRUST_TIER_AGGREGATED_MEDIA
        > TRUST_TIER_UNVERIFIED
    )


# ---------------------------------------------------------------------------
# compute_reliability_score
# ---------------------------------------------------------------------------


def _make_source(source_tier: str, health_score: float = 1.0) -> MagicMock:
    src = MagicMock()
    src.source_tier = source_tier
    src.health_score = health_score
    return src


def test_court_record_full_health_score():
    src = _make_source("court_record", health_score=1.0)
    assert compute_reliability_score(src) == 1.0


def test_unverified_full_health_score():
    src = _make_source("scraped_media", health_score=1.0)
    # 1 / 5 = 0.2
    assert compute_reliability_score(src) == pytest.approx(0.2, abs=1e-4)


def test_police_open_data_full_health():
    src = _make_source("official_police_open_data", health_score=1.0)
    # 4 / 5 = 0.8
    assert compute_reliability_score(src) == pytest.approx(0.8, abs=1e-4)


def test_zero_health_always_zero_reliability():
    for tier in ("court_record", "official_police_open_data", "scraped_media"):
        src = _make_source(tier, health_score=0.0)
        assert compute_reliability_score(src) == pytest.approx(0.0, abs=1e-6)


def test_reliability_score_clamped_above_one():
    """health_score > 1.0 should not produce a reliability_score > 1.0."""
    src = _make_source("court_record", health_score=2.0)
    assert compute_reliability_score(src) <= 1.0


def test_reliability_score_clamped_below_zero():
    """Negative health_score should not produce a negative reliability_score."""
    src = _make_source("court_record", health_score=-3.0)
    assert compute_reliability_score(src) >= 0.0


def test_unknown_tier_reliability_uses_unverified_weight():
    src = _make_source("unknown_tier", health_score=1.0)
    # TRUST_TIER_UNVERIFIED / TRUST_TIER_PRIMARY_OFFICIAL = 1/5
    expected = TRUST_TIER_UNVERIFIED / TRUST_TIER_PRIMARY_OFFICIAL
    assert compute_reliability_score(src) == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# resolve_conflict
# ---------------------------------------------------------------------------


def test_resolve_keeps_existing_when_incoming_lower():
    val, label = resolve_conflict(
        "court_value", "news_value", existing_tier=5, incoming_tier=2
    )
    assert val == "court_value"
    assert label == "kept_existing"


def test_resolve_accepts_incoming_when_incoming_higher():
    val, label = resolve_conflict(
        "old_low", "new_high", existing_tier=1, incoming_tier=5
    )
    assert val == "new_high"
    assert label == "accepted_incoming"


def test_resolve_keeps_existing_on_equal_tiers():
    val, label = resolve_conflict(
        "existing", "incoming", existing_tier=3, incoming_tier=3
    )
    assert val == "existing"
    assert label == "kept_existing"


# ---------------------------------------------------------------------------
# SourceTierConflict model (via db_session)
# ---------------------------------------------------------------------------


def test_source_tier_conflict_model_persists(db_session):
    """SourceTierConflict rows can be created and queried in the test DB."""
    from app.models.entities import SourceRegistry, SourceTierConflict

    # Use first two SourceRegistry rows created by seed_sample_data
    sources = db_session.query(SourceRegistry).limit(2).all()
    if len(sources) < 2:
        pytest.skip("Need at least 2 SourceRegistry rows from seed data")

    conflict = SourceTierConflict(
        incoming_source_id=sources[1].id,
        authoritative_source_id=sources[0].id,
        entity_type="event",
        entity_id=None,
        field_name="title",
        existing_value="existing text",
        incoming_value="incoming text",
        resolution="kept_existing",
        resolution_reason="authoritative source outranks incoming",
    )
    db_session.add(conflict)
    db_session.flush()

    found = db_session.query(SourceTierConflict).filter_by(field_name="title").first()
    assert found is not None
    assert found.resolution == "kept_existing"
    assert found.existing_value == "existing text"
    assert found.incoming_value == "incoming text"


# ---------------------------------------------------------------------------
# record_conflict helper
# ---------------------------------------------------------------------------


def test_record_conflict_persists_from_dict(db_session):
    """record_conflict() creates a SourceTierConflict from a plain dict."""
    from app.models.entities import SourceRegistry, SourceTierConflict

    sources = db_session.query(SourceRegistry).limit(2).all()
    if len(sources) < 2:
        pytest.skip("Need at least 2 SourceRegistry rows from seed data")

    data = {
        "incoming_source_id": sources[1].id,
        "authoritative_source_id": sources[0].id,
        "entity_type": "event",
        "entity_id": 42,
        "field_name": "summary",
        "existing_value": "official summary",
        "incoming_value": "news summary",
        "resolution": "kept_existing",
        "resolution_reason": "test",
    }
    conflict = record_conflict(data, db_session)
    assert conflict.id is not None
    assert conflict.field_name == "summary"
    assert conflict.entity_id == 42


def test_record_conflict_defaults_resolution(db_session):
    """record_conflict() defaults resolution to 'kept_existing' when not supplied."""
    from app.models.entities import SourceRegistry, SourceTierConflict

    sources = db_session.query(SourceRegistry).limit(2).all()
    if len(sources) < 2:
        pytest.skip("Need at least 2 SourceRegistry rows from seed data")

    data = {
        "incoming_source_id": sources[1].id,
        "authoritative_source_id": sources[0].id,
        "entity_type": "case",
        "field_name": "caption",
        "existing_value": "A",
        "incoming_value": "B",
    }
    conflict = record_conflict(data, db_session)
    assert conflict.resolution == "kept_existing"


# ---------------------------------------------------------------------------
# detect_conflicts: early-exit branches (no DB modification)
# ---------------------------------------------------------------------------


def test_detect_conflicts_returns_empty_for_unknown_source_id(db_session):
    """detect_conflicts returns [] when the incoming_source_id does not exist."""
    parsed = MagicMock()
    parsed.docket_number = "1:99-cv-00001"
    result = detect_conflicts(db_session, parsed, incoming_source_id=999999)
    assert result == []


def test_detect_conflicts_returns_empty_for_missing_docket(db_session):
    """detect_conflicts returns [] when the parsed record has no docket_number."""
    from app.models.entities import SourceRegistry

    source = db_session.query(SourceRegistry).first()
    if source is None:
        pytest.skip("Need at least 1 SourceRegistry row")

    parsed = MagicMock()
    parsed.docket_number = None
    result = detect_conflicts(db_session, parsed, incoming_source_id=source.id)
    assert result == []


def test_detect_conflicts_returns_empty_when_no_matching_case(db_session):
    """detect_conflicts returns [] when no existing case matches the docket."""
    from app.models.entities import SourceRegistry

    source = db_session.query(SourceRegistry).first()
    if source is None:
        pytest.skip("Need at least 1 SourceRegistry row")

    parsed = MagicMock()
    parsed.docket_number = "TOTALLY-NONEXISTENT-DOCKET-99999"
    result = detect_conflicts(db_session, parsed, incoming_source_id=source.id)
    assert result == []
