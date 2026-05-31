"""Phase 8 — Public map API hardening tests.

Verifies:
- is_public_crime_incident_mappable blocks unsafe precision levels
- _parse_bbox rejects oversized or malformed bounding boxes
- /api/map/crime-incidents excludes incidents with unsafe precision at query level
"""
from unittest.mock import MagicMock

from app.api.routes.map import _MAX_BBOX_AREA_SQ_DEG, _parse_bbox
from app.serializers.public import is_public_crime_incident_mappable
from app.services.publish_rules import BLOCKED_PRECISION_LEVELS, UNSAFE_MAP_PRECISIONS


# ---------------------------------------------------------------------------
# UNSAFE_MAP_PRECISIONS constant
# ---------------------------------------------------------------------------

def test_unsafe_map_precisions_is_superset_of_blocked():
    """UNSAFE_MAP_PRECISIONS must include every value from BLOCKED_PRECISION_LEVELS."""
    assert BLOCKED_PRECISION_LEVELS.issubset(UNSAFE_MAP_PRECISIONS)


def test_unsafe_map_precisions_includes_geocoder_labels():
    for label in ("rooftop", "parcel", "residential", "exact", "address_level"):
        assert label in UNSAFE_MAP_PRECISIONS, f"Expected '{label}' in UNSAFE_MAP_PRECISIONS"


# ---------------------------------------------------------------------------
# is_public_crime_incident_mappable — precision guard
# ---------------------------------------------------------------------------

def _make_incident(precision_level: str, review_status: str = "official_police_open_data_report") -> MagicMock:
    """Return a minimal CrimeIncident mock with is_public=True and valid coords."""
    inc = MagicMock()
    inc.is_public = True
    inc.review_status = review_status
    inc.latitude_public = 43.65
    inc.longitude_public = -79.38
    inc.precision_level = precision_level
    return inc


def test_mappable_allows_city_centroid():
    assert is_public_crime_incident_mappable(_make_incident("city_centroid")) is True


def test_mappable_allows_general_area():
    assert is_public_crime_incident_mappable(_make_incident("general_area")) is True


def test_mappable_allows_neighbourhood_centroid():
    assert is_public_crime_incident_mappable(_make_incident("neighbourhood_centroid")) is True


def test_mappable_blocks_exact_address():
    assert is_public_crime_incident_mappable(_make_incident("exact_address")) is False


def test_mappable_blocks_exact_residence():
    assert is_public_crime_incident_mappable(_make_incident("exact_residence")) is False


def test_mappable_blocks_home_address():
    assert is_public_crime_incident_mappable(_make_incident("home_address")) is False


def test_mappable_blocks_rooftop():
    assert is_public_crime_incident_mappable(_make_incident("rooftop")) is False


def test_mappable_blocks_parcel():
    assert is_public_crime_incident_mappable(_make_incident("parcel")) is False


def test_mappable_blocks_residential():
    assert is_public_crime_incident_mappable(_make_incident("residential")) is False


def test_mappable_blocks_not_public():
    inc = _make_incident("city_centroid")
    inc.is_public = False
    assert is_public_crime_incident_mappable(inc) is False


def test_mappable_blocks_zero_coords():
    inc = _make_incident("city_centroid")
    inc.latitude_public = 0.0
    assert is_public_crime_incident_mappable(inc) is False


# ---------------------------------------------------------------------------
# _parse_bbox — size cap and invalid-input guards
# ---------------------------------------------------------------------------

def test_parse_bbox_none_returns_none():
    assert _parse_bbox(None) is None


def test_parse_bbox_valid_small():
    result = _parse_bbox("-79.5,43.5,-79.0,44.0")
    assert result == (-79.5, 43.5, -79.0, 44.0)


def test_parse_bbox_rejects_oversized():
    from fastapi import HTTPException
    import pytest
    # 180° × 180° = 32 400 sq degrees, well over limit
    with pytest.raises(HTTPException) as exc_info:
        _parse_bbox("-180,-90,180,90")
    assert exc_info.value.status_code == 422
    assert "exceeds maximum" in exc_info.value.detail


def test_parse_bbox_at_exact_limit_passes():
    """A bbox of exactly _MAX_BBOX_AREA_SQ_DEG should not be rejected."""
    import math
    side = math.sqrt(_MAX_BBOX_AREA_SQ_DEG)
    result = _parse_bbox(f"0,0,{side},{side}")
    assert result is not None


def test_parse_bbox_south_gt_north_rejected():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc_info:
        _parse_bbox("-10,50,-5,40")
    assert exc_info.value.status_code == 422


def test_parse_bbox_non_numeric_rejected():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc_info:
        _parse_bbox("a,b,c,d")
    assert exc_info.value.status_code == 422


def test_parse_bbox_wrong_part_count_rejected():
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc_info:
        _parse_bbox("-79.5,43.5,-79.0")
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# /api/map/crime-incidents — blocked precision excluded from response
# ---------------------------------------------------------------------------

def test_crime_incidents_excludes_exact_address_precision(client):
    """Incidents with exact_address precision must not appear in map response."""
    from app.db.session import SessionLocal
    from app.models.entities import CrimeIncident

    # Insert a public incident with blocked precision
    with SessionLocal() as db:
        bad_incident = CrimeIncident(
            incident_type="test",
            incident_category="test",
            is_public=True,
            review_status="official_police_open_data_report",
            latitude_public=43.70,
            longitude_public=-79.40,
            precision_level="exact_address",
            source_name="toronto_police",
            verification_status="reported",
        )
        db.add(bad_incident)
        db.commit()
        bad_id = bad_incident.id

    response = client.get("/api/map/crime-incidents")
    assert response.status_code == 200
    ids_returned = [f["properties"]["incident_id"] for f in response.json()["features"]]
    assert bad_id not in ids_returned, "exact_address incident must not appear on public map"
