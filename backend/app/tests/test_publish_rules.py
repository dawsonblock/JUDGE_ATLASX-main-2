"""Tests for the publish_rules classification service."""

from app.services.publish_rules import (
    TIER_AUTO,
    TIER_BLOCK,
    TIER_HOLD,
    classify_record,
    public_visibility_for_tier,
    review_status_for_tier,
    source_tier,
    is_publishable,
    check_publication_safety,
)

# ---------------------------------------------------------------------------
# source_tier lookup
# ---------------------------------------------------------------------------


def test_source_tier_auto_publish_safe_sources():
    for name in [
        "natural_earth",
        "geonames",
        "court_location_registry",
        "statistics_canada",
        "fbi_crime_data",
        "chicago_data_portal",
        "toronto_police",
        "los_angeles_open_data",
    ]:
        assert source_tier(name) == TIER_AUTO, f"{name} should be TIER_AUTO"


def test_source_tier_hold_sources():
    for name in ["courtlistener", "gdelt", "news", "media_cloud", "court_opinion_rss", "saskatoon_police"]:
        assert source_tier(name) == TIER_HOLD, f"{name} should be TIER_HOLD"


def test_source_tier_unknown_defaults_to_hold():
    assert source_tier("some_random_source") == TIER_HOLD


# ---------------------------------------------------------------------------
# classify_record — tier passthrough
# ---------------------------------------------------------------------------


def test_classify_auto_source_clean_record_returns_auto():
    record = {"precision_level": "city_centroid", "notes": None}
    assert classify_record("statistics_canada", record) == TIER_AUTO


def test_classify_hold_source_clean_record_returns_hold():
    record = {"precision_level": "city_centroid", "notes": None}
    assert classify_record("courtlistener", record) == TIER_HOLD


def test_classify_gdelt_source_always_hold():
    record = {"precision_level": "city_centroid", "notes": "Court ruling article."}
    assert classify_record("gdelt", record) == TIER_HOLD


# ---------------------------------------------------------------------------
# classify_record — block patterns
# ---------------------------------------------------------------------------


def test_classify_blocks_exact_address_in_notes():
    record = {
        "precision_level": "city_centroid",
        "notes": "Incident occurred at 123 Main Street.",
    }
    assert classify_record("chicago_data_portal", record) == TIER_BLOCK


def test_classify_blocks_causal_judge_language():
    record = {
        "precision_level": "city_centroid",
        "notes": "Judge Smith caused the crime wave.",
    }
    assert classify_record("statistics_canada", record) == TIER_BLOCK


def test_classify_blocks_social_media_text():
    record = {
        "precision_level": "city_centroid",
        "docket_text": "Based on a tweet by the defendant.",
    }
    assert classify_record("courtlistener", record) == TIER_BLOCK


def test_classify_blocks_defendant_name_in_docket_text():
    record = {
        "precision_level": "city_centroid",
        "docket_text": "Defendant John Smith sentenced.",
    }
    assert classify_record("courtlistener", record) == TIER_BLOCK


# ---------------------------------------------------------------------------
# classify_record — auto→hold bumps for person names / exact precision
# ---------------------------------------------------------------------------


def test_classify_auto_source_bumps_to_hold_with_judge_name():
    record = {"precision_level": "city_centroid", "judge_name": "Hon. Alice Doe"}
    assert classify_record("chicago_data_portal", record) == TIER_HOLD


def test_classify_auto_source_bumps_to_hold_with_exact_precision():
    record = {"precision_level": "exact_address", "notes": None}
    assert classify_record("fbi_crime_data", record) == TIER_HOLD


def test_classify_auto_source_bumps_to_hold_with_parties():
    record = {"precision_level": "city_centroid", "parties": [{"name": "Someone"}]}
    assert classify_record("statistics_canada", record) == TIER_HOLD


# ---------------------------------------------------------------------------
# review_status_for_tier / public_visibility_for_tier
# ---------------------------------------------------------------------------


def test_review_status_auto():
    assert review_status_for_tier(TIER_AUTO) == "official_police_open_data_report"


def test_review_status_hold():
    assert review_status_for_tier(TIER_HOLD) == "pending_review"


def test_public_visibility_auto():
    assert public_visibility_for_tier(TIER_AUTO) is True


def test_public_visibility_hold():
    assert public_visibility_for_tier(TIER_HOLD) is False


def test_public_visibility_block():
    assert public_visibility_for_tier(TIER_BLOCK) is False


# ---------------------------------------------------------------------------
# is_publishable — publication gate tests
# ---------------------------------------------------------------------------


def test_is_publishable_valid_record_passes():
    """A complete valid record should be publishable."""
    record = {
        "source_url": "https://example.com/court-record/123",
        "source_tier": "court_record",
        "precision_level": "city_centroid",
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is True
    assert reasons == []


def test_is_publishable_missing_source_url_blocked():
    """Missing source_url should block publication."""
    record = {
        "source_url": None,
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert "missing_source_url" in reasons


def test_is_publishable_empty_source_url_blocked():
    """Empty source_url string should block publication."""
    record = {
        "source_url": "   ",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert "missing_source_url" in reasons


def test_is_publishable_invalid_source_tier_blocked():
    """Invalid source_tier should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "random_blog",
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert any("invalid_source_tier" in r for r in reasons)


def test_is_publishable_private_address_precision_blocked():
    """Exact private address precision should block publication."""
    for bad_precision in ["exact_private_address", "exact_residence", "home_address"]:
        record = {
            "source_url": "https://example.com/record",
            "source_tier": "official_police_open_data",
            "precision_level": bad_precision,
            "review_status": "official_police_open_data_report",
            "public_visibility": True,
        }
        is_ok, reasons = is_publishable(record)
        assert is_ok is False, f"Should block precision: {bad_precision}"
        assert any("blocked_precision" in r for r in reasons)


def test_is_publishable_safe_precision_allowed():
    """General area precision should be allowed."""
    for good_precision in ["city_centroid", "neighbourhood", "general_area"]:
        record = {
            "source_url": "https://example.com/record",
            "source_tier": "official_police_open_data",
            "precision_level": good_precision,
            "review_status": "official_police_open_data_report",
            "public_visibility": True,
        }
        is_ok, reasons = is_publishable(record)
        assert is_ok is True, f"Should allow precision: {good_precision}"


def test_is_publishable_pending_review_blocked():
    """Pending review status should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "pending_review",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert any("unapproved_status" in r for r in reasons)


def test_is_publishable_rejected_status_blocked():
    """Rejected status should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "rejected",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert any("unapproved_status" in r for r in reasons)


def test_is_publishable_public_visibility_false_blocked():
    """False public_visibility should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": False,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert "public_visibility_false" in reasons


def test_is_publishable_unresolved_safety_flags_blocked():
    """Unresolved safety flags should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": True,
        "safety_flags": [
            {"type": "privacy_risk", "resolved": False},
            {"type": "data_quality", "resolved": True},
        ],
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert any("unresolved_safety_flags" in r for r in reasons)


def test_is_publishable_resolved_safety_flags_allowed():
    """Resolved safety flags should not block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": True,
        "safety_flags": [
            {"type": "privacy_risk", "resolved": True},
        ],
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is True


def test_is_publishable_unsupported_linkage_blocked():
    """Unsupported judge/crime linkage should block publication."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "public_visibility": True,
        "judge_crime_linkage_status": "inferred_unsupported",
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is False
    assert "unsupported_judge_crime_linkage" in reasons


def test_is_publishable_source_quality_fallback():
    """source_quality field should be used as fallback for source_tier."""
    record = {
        "source_url": "https://example.com/record",
        "source_quality": "court_record",  # Using source_quality instead of source_tier
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is True


def test_is_publishable_is_public_fallback():
    """is_public field should be used as fallback for public_visibility."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "review_status": "verified_court_record",
        "is_public": True,  # Using is_public instead of public_visibility
    }
    is_ok, reasons = is_publishable(record)
    assert is_ok is True


# ---------------------------------------------------------------------------
# check_publication_safety — detailed report tests
# ---------------------------------------------------------------------------


def test_check_publication_safety_returns_full_report():
    """check_publication_safety should return detailed safety report."""
    record = {
        "source_url": "https://example.com/record",
        "source_tier": "court_record",
        "precision_level": "city_centroid",
        "review_status": "verified_court_record",
        "public_visibility": True,
    }
    report = check_publication_safety(record)
    assert report["safe_to_publish"] is True
    assert report["can_be_public"] is True
    assert report["blocking_reasons"] == []
    assert report["checks"]["has_source_url"] is True
    assert report["checks"]["valid_source_tier"] is True
    assert report["checks"]["safe_precision"] is True
    assert report["checks"]["approved_status"] is True
    assert report["checks"]["public_visibility_enabled"] is True


def test_check_publication_safety_reports_blocking_reasons():
    """check_publication_safety should report all blocking reasons."""
    record = {
        "source_url": None,
        "source_tier": "invalid_tier",
        "precision_level": "exact_private_address",
        "review_status": "pending_review",
        "public_visibility": False,
    }
    report = check_publication_safety(record)
    assert report["safe_to_publish"] is False
    assert len(report["blocking_reasons"]) >= 4  # Multiple issues
    assert report["checks"]["has_source_url"] is False
    assert report["checks"]["valid_source_tier"] is False
    assert report["checks"]["safe_precision"] is False
    assert report["checks"]["approved_status"] is False
    assert report["checks"]["public_visibility_enabled"] is False


# ---------------------------------------------------------------------------
# resolve_publication_policy — registry-aware publish policy
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402 (placed near usage)

from app.services.publish_rules import resolve_publication_policy  # noqa: E402


def _make_registry_db(source_row=None):
    """Mock DB: query().filter_by().first() returns source_row."""
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = source_row
    return db


def _make_source_row(
    is_active=True,
    requires_manual_review=False,
    auto_publish_enabled=True,
):
    row = MagicMock()
    row.is_active = is_active
    row.requires_manual_review = requires_manual_review
    row.auto_publish_enabled = auto_publish_enabled
    return row


def test_resolve_policy_registry_missing_returns_hold():
    db = _make_registry_db(source_row=None)
    assert resolve_publication_policy(db, "unknown_key", "Unknown") == TIER_HOLD


def test_resolve_policy_inactive_source_returns_hold():
    db = _make_registry_db(_make_source_row(is_active=False))
    assert resolve_publication_policy(db, "toronto_police", "toronto_police") == TIER_HOLD


def test_resolve_policy_requires_review_returns_hold():
    db = _make_registry_db(_make_source_row(requires_manual_review=True))
    assert resolve_publication_policy(db, "courtlistener", "courtlistener") == TIER_HOLD


def test_resolve_policy_auto_publish_disabled_returns_hold():
    db = _make_registry_db(_make_source_row(auto_publish_enabled=False))
    assert resolve_publication_policy(db, "web_monitor", "web_monitor") == TIER_HOLD


def test_resolve_policy_all_clear_delegates_to_source_tier():
    """When registry fully permits, result should match source_tier() lookup."""
    db = _make_registry_db(_make_source_row())
    result = resolve_publication_policy(db, "toronto_police", "toronto_police")
    # toronto_police is not in the static hold/block list → TIER_AUTO
    assert result == TIER_AUTO


# ---------------------------------------------------------------------------
# resolve_publication_policy — integration tests using real SQLite test DB
# ---------------------------------------------------------------------------


def _upsert_test_registry_row(
    db,
    source_key: str,
    source_name: str,
    *,
    is_active: bool = True,
    auto_publish_enabled: bool = True,
    requires_manual_review: bool = False,
):
    from app.models.entities import SourceRegistry

    row = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if row is None:
        row = SourceRegistry(
            source_key=source_key,
            source_name=source_name,
            source_tier="official_police_open_data",
            is_active=is_active,
            auto_publish_enabled=auto_publish_enabled,
            requires_manual_review=requires_manual_review,
        )
        db.add(row)
    else:
        row.source_name = source_name
        row.is_active = is_active
        row.auto_publish_enabled = auto_publish_enabled
        row.requires_manual_review = requires_manual_review
    db.commit()
    return row


def test_resolve_policy_real_db_unknown_source_fails_closed():
    """Unknown source (no registry row) must return TIER_HOLD with real DB."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        tier = resolve_publication_policy(
            db,
            source_key="__absolutely_no_such_key__",
            source_name="__absolutely_no_such_name__",
        )
    assert tier == TIER_HOLD


def test_resolve_policy_third_fallback_finds_row_by_source_name():
    """Third fallback: when source_key has no matching row but source_name does,
    the registry row is found and its policy is applied.

    Row: source_key='_fb3p_rkey', source_name='natural_earth'
    Call: source_key='natural_earth', source_name='natural_earth'
      → 1st filter_by(source_key='natural_earth') → None
      → 2nd fallback skipped (source_key == source_name)
      → 3rd filter_by(source_name='natural_earth') → finds row
      → row permissive → source_tier('natural_earth') == TIER_AUTO
    """
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        _upsert_test_registry_row(
            db,
            source_key="_fb3p_rkey",
            source_name="natural_earth",
            is_active=True,
            auto_publish_enabled=True,
            requires_manual_review=False,
        )
        tier = resolve_publication_policy(
            db,
            source_key="natural_earth",
            source_name="natural_earth",
        )
    assert tier == TIER_AUTO


def test_resolve_policy_real_db_inactive_returns_hold():
    """Inactive registry row must return TIER_HOLD with real DB."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        _upsert_test_registry_row(
            db,
            source_key="_fb3p_inactive_key",
            source_name="_fb3p_inactive_sname",
            is_active=False,
            auto_publish_enabled=True,
            requires_manual_review=False,
        )
        tier = resolve_publication_policy(
            db,
            source_key="_fb3p_inactive_key",
            source_name="_fb3p_inactive_sname",
        )
    assert tier == TIER_HOLD
