"""Verify that the serializer-layer public-API gate functions enforce boundaries.

These tests cover the *real* gatekeeper functions in app.serializers.public and
app.services.constants — the layer that decides whether a DB row may cross the
public-API boundary.  The companion file test_public_api_boundary.py tests
pure in-memory filter logic with a synthetic dataclass; this file tests the
actual functions called by the live routes.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.serializers.public import (
    is_public_crime_incident,
    is_public_crime_incident_mappable,
    is_public_event,
    is_public_source,
)
from app.services.constants import (
    NON_PUBLIC_REVIEW_STATUSES,
    PUBLIC_REVIEW_STATUSES,
    REVIEW_STATUSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(*, public_visibility: bool, review_status: str) -> SimpleNamespace:
    return SimpleNamespace(public_visibility=public_visibility, review_status=review_status)


def _source(*, public_visibility: bool, review_status: str) -> SimpleNamespace:
    return SimpleNamespace(public_visibility=public_visibility, review_status=review_status)


def _incident(
    *,
    is_public: bool,
    review_status: str,
    latitude_public: float | None = 45.0,
    longitude_public: float | None = -75.0,
    precision_level: str | None = "neighbourhood",
) -> SimpleNamespace:
    return SimpleNamespace(
        is_public=is_public,
        review_status=review_status,
        latitude_public=latitude_public,
        longitude_public=longitude_public,
        precision_level=precision_level,
    )


# ---------------------------------------------------------------------------
# Status-set invariants
# ---------------------------------------------------------------------------


def test_public_and_non_public_statuses_are_disjoint() -> None:
    """No status may appear in both sets — an overlap would be a logic bomb."""
    overlap = PUBLIC_REVIEW_STATUSES & NON_PUBLIC_REVIEW_STATUSES
    assert overlap == set(), f"Overlapping statuses: {overlap}"


def test_public_statuses_are_subset_of_review_statuses() -> None:
    assert PUBLIC_REVIEW_STATUSES <= REVIEW_STATUSES


def test_non_public_statuses_are_subset_of_review_statuses() -> None:
    assert NON_PUBLIC_REVIEW_STATUSES <= REVIEW_STATUSES


# ---------------------------------------------------------------------------
# is_public_event
# ---------------------------------------------------------------------------


def test_is_public_event_returns_true_when_visibility_and_valid_status() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert is_public_event(_event(public_visibility=True, review_status=status)), status


def test_is_public_event_returns_false_when_not_visible() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert not is_public_event(_event(public_visibility=False, review_status=status)), status


def test_is_public_event_returns_false_for_non_public_statuses() -> None:
    for status in NON_PUBLIC_REVIEW_STATUSES:
        assert not is_public_event(_event(public_visibility=True, review_status=status)), status


def test_is_public_event_returns_false_for_none() -> None:
    assert not is_public_event(None)


# ---------------------------------------------------------------------------
# is_public_source
# ---------------------------------------------------------------------------


def test_is_public_source_returns_true_when_visibility_and_valid_status() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert is_public_source(_source(public_visibility=True, review_status=status)), status


def test_is_public_source_returns_false_when_not_visible() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert not is_public_source(_source(public_visibility=False, review_status=status)), status


def test_is_public_source_returns_false_for_non_public_statuses() -> None:
    for status in NON_PUBLIC_REVIEW_STATUSES:
        assert not is_public_source(_source(public_visibility=True, review_status=status)), status


def test_is_public_source_returns_false_for_none() -> None:
    assert not is_public_source(None)


# ---------------------------------------------------------------------------
# is_public_crime_incident
# ---------------------------------------------------------------------------


def test_is_public_crime_incident_returns_true_when_public_and_valid_status() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert is_public_crime_incident(_incident(is_public=True, review_status=status)), status


def test_is_public_crime_incident_returns_false_when_not_public() -> None:
    for status in PUBLIC_REVIEW_STATUSES:
        assert not is_public_crime_incident(
            _incident(is_public=False, review_status=status)
        ), status


def test_is_public_crime_incident_returns_false_for_non_public_statuses() -> None:
    for status in NON_PUBLIC_REVIEW_STATUSES:
        assert not is_public_crime_incident(
            _incident(is_public=True, review_status=status)
        ), status


def test_is_public_crime_incident_returns_false_for_none() -> None:
    assert not is_public_crime_incident(None)


# ---------------------------------------------------------------------------
# is_public_crime_incident_mappable
# ---------------------------------------------------------------------------


def test_mappable_incident_with_safe_precision_and_valid_coords() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        latitude_public=45.0,
        longitude_public=-75.0,
        precision_level="neighbourhood",
    )
    assert is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_when_not_public() -> None:
    inc = _incident(
        is_public=False,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
    )
    assert not is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_when_coords_are_none() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        latitude_public=None,
        longitude_public=None,
    )
    assert not is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_when_coords_are_zero() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        latitude_public=0.0,
        longitude_public=0.0,
    )
    assert not is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_for_rooftop_precision() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        precision_level="rooftop",
    )
    assert not is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_for_exact_precision() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        precision_level="exact_location",
    )
    assert not is_public_crime_incident_mappable(inc)


def test_mappable_incident_blocked_for_address_precision() -> None:
    inc = _incident(
        is_public=True,
        review_status=next(iter(PUBLIC_REVIEW_STATUSES)),
        precision_level="address_level",
    )
    assert not is_public_crime_incident_mappable(inc)
