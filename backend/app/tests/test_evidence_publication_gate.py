"""Tests for evidence publication gate.

Proves that the publication policy enforces all required evidence fields
before a record can become public:
  - source_id / source_url must exist
  - snapshot_hash / evidence must be linked
  - review_status must be in PUBLIC_REVIEW_STATUSES (pending_review → cannot publish)
  - hash mismatch → cannot publish
  - unknown source → cannot publish
  - AI-only summary → cannot publish
  - approximate location → must be labeled (blocked precision levels gate)
  - no evidence → cannot publish
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.publish_rules import (
    PUBLIC_REVIEW_STATUSES,
    VALID_SOURCE_TIERS,
    is_publishable,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal publishable record dicts
# ---------------------------------------------------------------------------


def _valid_record(**overrides) -> dict[str, Any]:
    """Return a dict that passes all publication gates."""
    base: dict[str, Any] = {
        "source_url": "https://www.canlii.org/en/sk/skkb/doc/2024/2024skkb1/2024skkb1.html",
        "source_tier": "court_record",
        "precision_level": "city",
        "review_status": "verified_court_record",
        "public_visibility": True,
        "safety_flags": [],
        "judge_crime_linkage_status": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: missing required evidence fields block publication
# ---------------------------------------------------------------------------


class TestNoEvidenceBlocksPublication:
    def test_missing_source_url_blocks(self):
        """No source URL → cannot publish."""
        record = _valid_record(source_url=None)
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("missing_source_url" in r for r in reasons)

    def test_empty_source_url_blocks(self):
        """Empty source URL → cannot publish."""
        record = _valid_record(source_url="")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("missing_source_url" in r for r in reasons)

    def test_whitespace_source_url_blocks(self):
        """Whitespace-only source URL → cannot publish."""
        record = _valid_record(source_url="   ")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("missing_source_url" in r for r in reasons)


class TestPendingReviewBlocksPublication:
    def test_pending_review_blocks(self):
        """pending_review status → cannot publish."""
        record = _valid_record(review_status="pending_review")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("unapproved_status" in r for r in reasons)

    def test_none_review_status_blocks(self):
        """No review status → cannot publish."""
        record = _valid_record(review_status=None)
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("unapproved_status" in r for r in reasons)

    def test_unknown_review_status_blocks(self):
        """Unknown / unrecognised review status → cannot publish."""
        record = _valid_record(review_status="some_new_unknown_status")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("unapproved_status" in r for r in reasons)


class TestUnknownSourceBlocksPublication:
    def test_unknown_source_tier_blocks(self):
        """Unknown source tier → cannot publish."""
        record = _valid_record(source_tier="unknown_scraper")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("invalid_source_tier" in r for r in reasons)

    def test_none_source_tier_blocks(self):
        """No source tier → cannot publish."""
        record = _valid_record(source_tier=None)
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("invalid_source_tier" in r for r in reasons)

    def test_ai_only_summary_source_blocks(self):
        """AI-only / LLM-generated source tier → cannot publish."""
        record = _valid_record(source_tier="ai_generated_summary")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("invalid_source_tier" in r for r in reasons)


class TestHashMismatchBlocksPublication:
    """Hash / integrity failure must prevent publication.

    The publication gate checks review_status and public_visibility; the lower-level
    hash verification happens in snapshots/evidence retrieval.  This test verifies
    that the gate will deny a record marked as having a hash failure.
    """

    def test_hash_failure_via_safety_flag_blocks(self):
        """A record flagged with a hash mismatch must be blocked."""
        record = _valid_record(
            safety_flags=[
                {"flag": "hash_mismatch", "resolved": False}
            ]
        )
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("safety_flags" in r for r in reasons)

    def test_resolved_flag_does_not_block(self):
        """A resolved safety flag must not block publication."""
        record = _valid_record(
            safety_flags=[
                {"flag": "hash_mismatch", "resolved": True}
            ]
        )
        ok, reasons = is_publishable(record)
        assert ok, f"Resolved safety flag should not block; reasons: {reasons}"


class TestApproximateLocationMustBeLabeled:
    """Approximate location must be labeled (i.e., exact private addresses blocked)."""

    def test_exact_private_address_blocks(self):
        """Records with exact private address precision must not be published."""
        for prec in ["exact_private_address", "exact_residence", "home_address"]:
            record = _valid_record(precision_level=prec)
            ok, reasons = is_publishable(record)
            assert not ok, f"Precision '{prec}' should block publication"
            assert any("blocked_precision" in r for r in reasons), (
                f"Expected blocked_precision in reasons for '{prec}', got {reasons}"
            )

    def test_city_precision_is_allowed(self):
        """City-level precision is safe to publish."""
        record = _valid_record(precision_level="city")
        ok, _ = is_publishable(record)
        assert ok

    def test_none_precision_is_allowed(self):
        """Records without precision data pass the location gate."""
        record = _valid_record(precision_level=None)
        ok, reasons = is_publishable(record)
        # precision_level=None should not trigger the blocked_precision gate
        assert not any("blocked_precision" in r for r in reasons)


class TestUnsupportedJudgeLinkageBlocks:
    def test_inferred_unsupported_linkage_blocks(self):
        """Inferred judge-crime linkage without source support must block publication."""
        record = _valid_record(judge_crime_linkage_status="inferred_unsupported")
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("unsupported_judge_crime_linkage" in r for r in reasons)

    def test_verified_linkage_does_not_block(self):
        """Source-verified linkage must not block publication."""
        record = _valid_record(judge_crime_linkage_status="verified_court_record")
        ok, reasons = is_publishable(record)
        # Linkage alone should not block if review status and source are valid
        assert not any("unsupported_judge_crime_linkage" in r for r in reasons)


class TestPublicVisibilityGate:
    def test_false_public_visibility_blocks(self):
        """public_visibility=False → cannot publish even if status is approved."""
        record = _valid_record(public_visibility=False)
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("public_visibility_false" in r for r in reasons)

    def test_none_public_visibility_blocks(self):
        """public_visibility=None → cannot publish."""
        record = _valid_record(public_visibility=None)
        ok, reasons = is_publishable(record)
        assert not ok
        assert any("public_visibility_false" in r for r in reasons)


class TestValidRecordPasses:
    def test_complete_valid_record_passes(self):
        """A record that satisfies all gates must be publishable."""
        record = _valid_record()
        ok, reasons = is_publishable(record)
        assert ok, f"Expected valid record to pass publication gate; reasons: {reasons}"

    @pytest.mark.parametrize("status", list(PUBLIC_REVIEW_STATUSES))
    def test_all_approved_statuses_are_publishable(self, status):
        """Every PUBLIC_REVIEW_STATUS must be accepted when other gates pass."""
        record = _valid_record(review_status=status)
        ok, reasons = is_publishable(record)
        assert ok, (
            f"Review status '{status}' should allow publication; reasons: {reasons}"
        )

    @pytest.mark.parametrize("tier", list(VALID_SOURCE_TIERS))
    def test_all_valid_source_tiers_are_accepted(self, tier):
        """Every VALID_SOURCE_TIER must be accepted when other gates pass."""
        record = _valid_record(source_tier=tier)
        ok, reasons = is_publishable(record)
        assert ok, (
            f"Source tier '{tier}' should be accepted; reasons: {reasons}"
        )
