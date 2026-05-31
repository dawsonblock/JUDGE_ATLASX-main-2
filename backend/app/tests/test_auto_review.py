"""Unit tests for app.services.auto_review — each gate tested independently."""

from datetime import datetime

import pytest

from app.ingestion.crime_sources.base import CrimeIncidentRecord
from app.services.auto_review import AutoReviewResult, auto_review

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 1, 1)


def _rec(**kwargs) -> CrimeIncidentRecord:
    """Build a minimal valid CrimeIncidentRecord with sane defaults."""
    defaults = dict(
        source_id="SRC-001",
        external_id="EXT-001",
        incident_type="assault",
        incident_category="violent",
        reported_at=_NOW,
        occurred_at=_NOW,
        city="Toronto",
        province_state="ON",
        country="CA",
        public_area_label="Downtown",
        latitude_public=43.65,
        longitude_public=-79.38,
        precision_level="city_centroid",
        source_url="https://example.com/incident/1",
        source_name="toronto_police",
        verification_status="verified",
        data_last_seen_at=_NOW,
        is_public=True,
        notes=None,
        is_aggregate=False,
    )
    defaults.update(kwargs)
    return CrimeIncidentRecord(**defaults)


# ---------------------------------------------------------------------------
# Gate 1: block patterns
# ---------------------------------------------------------------------------


def test_gate1_full_name_in_notes_blocks():
    record = _rec(notes="Suspect John Smith arrested at scene.")
    result = auto_review(
        record,
        "statistics_canada",
        has_snapshot_hash=True,
        official_identifier="FILE123",
    )
    assert result.action == "block"
    assert result.public_visibility is False


def test_gate1_home_address_blocks():
    record = _rec(notes="Incident at 123 Maple St, unit 4.")
    result = auto_review(record, "toronto_police", has_snapshot_hash=True)
    assert result.action == "block"


def test_gate1_clean_notes_does_not_block():
    record = _rec(notes="Officer responded to noise complaint.")
    result = auto_review(record, "statistics_canada", has_snapshot_hash=True)
    # Should not block on clean notes
    assert result.action != "block"


# ---------------------------------------------------------------------------
# Gate 2: context-only sources
# ---------------------------------------------------------------------------


def test_gate2_gdelt_is_context_only():
    record = _rec(source_name="gdelt", notes=None)
    result = auto_review(record, "gdelt", has_snapshot_hash=True)
    assert result.action == "context_only"
    assert result.public_visibility is False


def test_gate2_media_cloud_is_context_only():
    record = _rec(source_name="media_cloud", notes=None)
    result = auto_review(record, "media_cloud", has_snapshot_hash=True)
    assert result.action == "context_only"


def test_gate2_court_opinion_rss_is_context_only():
    record = _rec(source_name="court_opinion_rss", notes=None)
    result = auto_review(record, "court_opinion_rss", has_snapshot_hash=True)
    assert result.action == "context_only"


def test_gate2_trusted_source_not_context_only():
    record = _rec(source_name="toronto_police", notes=None)
    result = auto_review(record, "toronto_police", has_snapshot_hash=True)
    assert result.action != "context_only"


# ---------------------------------------------------------------------------
# Gate 4: snapshot hash
# ---------------------------------------------------------------------------


def test_gate4_snapshot_hash_boosts_confidence():
    record = _rec(notes=None)
    with_hash = auto_review(record, "statistics_canada", has_snapshot_hash=True)
    without_hash = auto_review(record, "statistics_canada", has_snapshot_hash=False)
    assert with_hash.confidence > without_hash.confidence


# ---------------------------------------------------------------------------
# Gate 6: coordinates
# ---------------------------------------------------------------------------


def test_gate6_missing_coordinates_lowers_confidence():
    record_no_coord = _rec(latitude_public=None, longitude_public=None, notes=None)
    record_with_coord = _rec(notes=None)
    result_no = auto_review(
        record_no_coord,
        "statistics_canada",
        has_snapshot_hash=True,
        official_identifier="X",
    )
    result_yes = auto_review(
        record_with_coord,
        "statistics_canada",
        has_snapshot_hash=True,
        official_identifier="X",
    )
    assert result_no.confidence < result_yes.confidence


def test_gate6_zero_coordinates_treated_as_missing():
    record = _rec(latitude_public=0.0, longitude_public=0.0, notes=None)
    result = auto_review(
        record, "statistics_canada", has_snapshot_hash=True, official_identifier="X"
    )
    # Should penalise confidence
    assert result.confidence < 1.0


# ---------------------------------------------------------------------------
# Gate 7: exact/address/residence precision → block
# ---------------------------------------------------------------------------


def test_gate7_exact_precision_blocks():
    record = _rec(precision_level="exact", notes=None)
    result = auto_review(record, "toronto_police", has_snapshot_hash=True)
    assert result.action == "block"


def test_gate7_address_precision_blocks():
    record = _rec(precision_level="address", notes=None)
    result = auto_review(record, "toronto_police", has_snapshot_hash=True)
    assert result.action == "block"


def test_gate7_residence_precision_blocks():
    record = _rec(precision_level="residence", notes=None)
    result = auto_review(record, "toronto_police", has_snapshot_hash=True)
    assert result.action == "block"


def test_gate7_city_centroid_does_not_block():
    record = _rec(precision_level="city_centroid", notes=None)
    result = auto_review(record, "statistics_canada", has_snapshot_hash=True)
    assert result.action != "block"


# ---------------------------------------------------------------------------
# Happy path: high-confidence record → private review-ready recommendation
# ---------------------------------------------------------------------------


def test_high_confidence_auto_review_stays_private():
    record = _rec(notes=None)
    result = auto_review(
        record,
        "statistics_canada",
        has_snapshot_hash=True,
        official_identifier="FILE-2025-001",
    )
    assert result.action == "review_ready"
    assert result.review_status == "pending_review"
    assert result.public_visibility is False
    assert result.confidence >= 0.70


# ---------------------------------------------------------------------------
# Quarantine path: HOLD-tier source
# ---------------------------------------------------------------------------


def test_hold_tier_source_quarantines():
    record = _rec(source_name="courtlistener", notes=None)
    result = auto_review(
        record,
        "courtlistener",
        has_snapshot_hash=True,
        official_identifier="FILE-X",
        db_tier="hold",
    )
    # HOLD tier reduces confidence → should not auto-publish
    assert result.action in ("quarantine", "context_only")
    assert result.public_visibility is False


# ---------------------------------------------------------------------------
# AutoReviewResult structure
# ---------------------------------------------------------------------------


def test_result_has_reasons_list():
    record = _rec(notes=None)
    result = auto_review(record, "statistics_canada")
    assert isinstance(result.reasons, list)
    assert isinstance(result.warnings, list)


def test_result_confidence_bounded():
    record = _rec(notes=None)
    result = auto_review(record, "statistics_canada", has_snapshot_hash=True)
    assert 0.0 <= result.confidence <= 1.0
