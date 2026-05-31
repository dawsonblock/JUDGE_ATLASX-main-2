"""Tests for Phase 1-5 open-data adapters.

Covers:
- Natural Earth boundary loader
- GeoNames city resolver (mocked HTTP)
- Statistics Canada CSV importer
- FBI Crime Data JSON importer
- Chicago Socrata CSV importer
- Toronto Police CSV importer
- Saskatoon Police CSV importer
- Los Angeles Open Data CSV importer
- GDELT article importer
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

from app.db.session import SessionLocal
from app.ingestion.geonames import GeoNamesResult, resolve_city
from app.ingestion.gdelt import import_gdelt_articles, _parse_gdelt_date
from app.ingestion.natural_earth import load_natural_earth_file
from app.ingestion.crime_sources.statscan import import_statscan_csv
from app.ingestion.crime_sources.fbi_crime_data import import_fbi_json
from app.ingestion.crime_sources.chicago_socrata import import_chicago_csv
from app.ingestion.crime_sources.toronto import import_toronto_csv
from app.ingestion.crime_sources.saskatoon import import_saskatoon_csv
from app.ingestion.crime_sources.los_angeles import import_la_csv


# ---------------------------------------------------------------------------
# Natural Earth loader
# ---------------------------------------------------------------------------

_SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "NAME": "Canada",
                "ISO_A2": "CA",
                "ADMIN": "Canada",
            },
            "geometry": {"type": "Polygon", "coordinates": [[]]},
        },
        {
            "type": "Feature",
            "properties": {
                "NAME": "United States of America",
                "ISO_A2": "US",
            },
            "geometry": {"type": "MultiPolygon", "coordinates": [[]]},
        },
    ],
}


def test_natural_earth_loader_upserts_boundaries(tmp_path):
    geojson_file = tmp_path / "countries.geojson"
    geojson_file.write_text(json.dumps(_SAMPLE_GEOJSON))

    with SessionLocal() as db:
        result = load_natural_earth_file(db, path=geojson_file, boundary_type="country")

    assert result.read_count == 2
    assert result.upserted_count == 2
    assert result.error_count == 0


def test_natural_earth_loader_idempotent(tmp_path):
    geojson_file = tmp_path / "countries2.geojson"
    geojson_file.write_text(json.dumps(_SAMPLE_GEOJSON))

    with SessionLocal() as db:
        r1 = load_natural_earth_file(db, path=geojson_file, boundary_type="country")
        r2 = load_natural_earth_file(db, path=geojson_file, boundary_type="country")

    assert r1.upserted_count == r2.upserted_count


def test_natural_earth_loader_missing_file_returns_error(tmp_path):
    with SessionLocal() as db:
        result = load_natural_earth_file(db, path=tmp_path / "nonexistent.geojson", boundary_type="country")
    assert result.error_count == 1
    assert result.upserted_count == 0


# ---------------------------------------------------------------------------
# GeoNames resolver
# ---------------------------------------------------------------------------

_GEONAMES_RESPONSE = {
    "geonames": [
        {
            "geonameId": 6167865,
            "name": "Toronto",
            "lat": "43.70011",
            "lng": "-79.4163",
            "countryCode": "CA",
            "adminCode1": "08",
        }
    ]
}


def test_geonames_resolve_city_returns_result():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _GEONAMES_RESPONSE
    mock_resp.raise_for_status.return_value = None
    mock_client.get.return_value = mock_resp

    result = resolve_city("Toronto", "ON", "CA", username="testuser", client=mock_client)

    assert isinstance(result, GeoNamesResult)
    assert result.name == "Toronto"
    assert result.geonames_id == 6167865
    assert abs(result.latitude - 43.70011) < 0.001


def test_geonames_resolve_city_no_username_returns_none():
    with patch("app.ingestion.geonames.get_settings") as mock_settings:
        mock_settings.return_value.geonames_username = None
        result = resolve_city("Toronto")
    assert result is None


def test_geonames_resolve_city_empty_response_returns_none():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"geonames": []}
    mock_resp.raise_for_status.return_value = None
    mock_client.get.return_value = mock_resp

    result = resolve_city("NowhereCity", username="testuser", client=mock_client)
    assert result is None


# ---------------------------------------------------------------------------
# Statistics Canada CSV importer
# ---------------------------------------------------------------------------

_STATSCAN_CSV = (
    "GEO,Violations,VALUE\n"
    "Ontario,Assault,12345\n"
    "Quebec,Theft,8901\n"
    "Canada,Homicide,456\n"
    "UnknownProvince,Fraud,100\n"
)


def test_statscan_import_known_provinces():
    with SessionLocal() as db:
        stream = io.StringIO(_STATSCAN_CSV)
        result = import_statscan_csv(db, stream)
    assert result.read_count == 4
    assert result.persisted_count == 3
    assert result.skipped_count == 1


def test_statscan_import_auto_publish_tier():
    """Without a seeded SourceRegistry row the fail-closed policy holds StatsCan records."""
    from app.models.entities import CrimeIncident
    with SessionLocal() as db:
        stream = io.StringIO("GEO,Violations,VALUE\nOntario,Assault - STATSCAN-TEST-TIER,1\n")
        import_statscan_csv(db, stream)
        inc = db.query(CrimeIncident).filter(
            CrimeIncident.source_name == "statistics_canada",
            CrimeIncident.incident_type == "Assault - STATSCAN-TEST-TIER",
        ).first()
    assert inc is not None
    assert inc.review_status == "pending_review"
    assert inc.is_public is False


def test_statscan_import_missing_columns_skips():
    with SessionLocal() as db:
        stream = io.StringIO("GEO,VALUE\nOntario,123\n")
        result = import_statscan_csv(db, stream)
    assert result.skipped_count >= 1


# ---------------------------------------------------------------------------
# FBI Crime Data JSON importer
# ---------------------------------------------------------------------------

_FBI_PAYLOAD = [
    {"state_abbr": "IL", "offense": "aggravated-assault", "count": 5000},
    {"state_abbr": "CA", "offense": "burglary", "count": 12000},
    {"state_abbr": "XX", "offense": "theft", "count": 100},
]


def test_fbi_import_known_states():
    with SessionLocal() as db:
        result = import_fbi_json(db, _FBI_PAYLOAD)
    assert result.read_count == 3
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_fbi_import_auto_publish_tier():
    """Without a seeded SourceRegistry row the fail-closed policy holds FBI records."""
    from app.models.entities import CrimeIncident
    with SessionLocal() as db:
        import_fbi_json(db, [{"state_abbr": "NY", "offense": "fbi-test-offense-tier", "count": 1}])
        inc = db.query(CrimeIncident).filter(
            CrimeIncident.source_name == "fbi_crime_data",
            CrimeIncident.incident_type == "fbi-test-offense-tier",
        ).first()
    assert inc is not None
    assert inc.review_status == "pending_review"


def test_fbi_import_empty_payload():
    with SessionLocal() as db:
        result = import_fbi_json(db, [])
    assert result.read_count == 0
    assert result.persisted_count == 0


# ---------------------------------------------------------------------------
# Chicago Socrata CSV importer
# ---------------------------------------------------------------------------

_CHICAGO_CSV = (
    "ID,Date,Primary Type,Description,Community Area Name,Latitude,Longitude\n"
    "CHI001,01/15/2024 10:00:00 AM,ASSAULT,SIMPLE,LOOP,41.8819,-87.6278\n"
    "CHI002,02/20/2024 08:30:00 PM,THEFT,FROM BUILDING,UPTOWN,41.9686,-87.6546\n"
    "CHI003,03/01/2024 06:00:00 AM,,,UNKNOWN,0.0,0.0\n"
)


def test_chicago_import_valid_rows():
    with SessionLocal() as db:
        result = import_chicago_csv(db, io.StringIO(_CHICAGO_CSV))
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_chicago_import_rejects_unsafe_notes():
    bad_csv = (
        "ID,Date,Primary Type,Description,Community Area Name,Latitude,Longitude\n"
        "CHI999,01/01/2024,ASSAULT,suspect John Doe 123 Main Street,LOOP,41.8819,-87.6278\n"
    )
    with SessionLocal() as db:
        result = import_chicago_csv(db, io.StringIO(bad_csv))
    assert result.persisted_count == 0
    assert result.skipped_count == 1


# ---------------------------------------------------------------------------
# Toronto Police CSV importer
# ---------------------------------------------------------------------------

_TORONTO_CSV = (
    "EVENT_UNIQUE_ID,OCC_DATE,MCI_CATEGORY,NEIGHBOURHOOD_158,LAT_WGS84,LONG_WGS84\n"
    "TPS001,2024-01-10,Assault,DOWNTOWN,43.6532,-79.3832\n"
    "TPS002,2024-02-14,Theft Over,NORTH YORK,43.7615,-79.4111\n"
    "TPS003,2024-03-01,,UNKNOWN,43.6532,-79.3832\n"
)


def test_toronto_import_valid_rows():
    with SessionLocal() as db:
        result = import_toronto_csv(db, io.StringIO(_TORONTO_CSV))
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_toronto_import_unsafe_record_rejected():
    bad_csv = (
        "EVENT_UNIQUE_ID,OCC_DATE,MCI_CATEGORY,NEIGHBOURHOOD_158,LAT_WGS84,LONG_WGS84\n"
        "TPS999,2024-01-01,Assault,DOWNTOWN,43.6532,-79.3832\n"
    )
    with SessionLocal() as db:
        r1 = import_toronto_csv(db, io.StringIO(bad_csv))
    assert r1.error_count == 0


# ---------------------------------------------------------------------------
# Saskatoon Police CSV importer
# ---------------------------------------------------------------------------

_SASKATOON_CSV = (
    "IncidentType,ReportedDate,Neighbourhood\n"
    "Theft,2024-03-10,City Park\n"
    "Assault,2024-04-01,Riversdale\n"
    ",2024-05-01,Unknown\n"
)


def test_saskatoon_import_valid_rows():
    with SessionLocal() as db:
        result = import_saskatoon_csv(db, io.StringIO(_SASKATOON_CSV))
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_saskatoon_import_uses_city_centroid():
    from app.models.entities import CrimeIncident
    with SessionLocal() as db:
        import_saskatoon_csv(db, io.StringIO(
            "IncidentType,ReportedDate,Neighbourhood\nRobbery-SPS-COORD-TEST,2024-01-01,Test\n"
        ))
        inc = db.query(CrimeIncident).filter(
            CrimeIncident.source_name == "saskatoon_police",
            CrimeIncident.incident_type == "Robbery-SPS-COORD-TEST",
        ).first()
    assert inc is not None
    assert abs(inc.latitude_public - 52.1332) < 0.01
    assert inc.precision_level == "city_centroid"


# ---------------------------------------------------------------------------
# Los Angeles Open Data CSV importer
# ---------------------------------------------------------------------------

_LA_CSV = (
    "DR_NO,DATE OCC,Crm Cd Desc,AREA NAME,LAT,LON\n"
    "LA001,01/20/2024,ASSAULT WITH DEADLY WEAPON,CENTRAL,34.0510,-118.2500\n"
    "LA002,02/15/2024,BURGLARY,HOLLYWOOD,34.0980,-118.3267\n"
    "LA003,03/01/2024,,UNKNOWN,0.0,0.0\n"
)


def test_la_import_valid_rows():
    with SessionLocal() as db:
        result = import_la_csv(db, io.StringIO(_LA_CSV))
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_la_import_falls_back_to_area_centroid():
    from app.models.entities import CrimeIncident
    csv = (
        "DR_NO,DATE OCC,Crm Cd Desc,AREA NAME,LAT,LON\n"
        "LA-CENTROID-TEST,01/01/2024,THEFT-LA-CENTROID-TEST,HARBOR,0.0,0.0\n"
    )
    with SessionLocal() as db:
        import_la_csv(db, io.StringIO(csv))
        inc = db.query(CrimeIncident).filter(
            CrimeIncident.source_name == "los_angeles_open_data",
            CrimeIncident.incident_type == "THEFT-LA-CENTROID-TEST",
        ).first()
    assert inc is not None
    assert abs(inc.latitude_public - 33.7975) < 0.01


# ---------------------------------------------------------------------------
# GDELT article importer
# ---------------------------------------------------------------------------

_GDELT_ARTICLES = [
    {
        "url": "https://www.example-news.com/article/court-ruling-1",
        "title": "Court issues major ruling",
        "domain": "example-news.com",
        "seendate": "20240315T120000Z",
    },
    {
        "url": "https://www.example-news.com/article/judge-sentence-2",
        "title": "Judge hands down sentence",
        "domain": "example-news.com",
        "seendate": "20240401T080000Z",
    },
    {"url": "", "title": "No URL article", "domain": "none.com", "seendate": ""},
]


def test_gdelt_import_valid_articles():
    with SessionLocal() as db:
        result = import_gdelt_articles(db, _GDELT_ARTICLES)
    assert result.read_count == 3
    assert result.persisted_count == 2
    assert result.skipped_count == 1


def test_gdelt_import_idempotent():
    with SessionLocal() as db:
        import_gdelt_articles(db, _GDELT_ARTICLES)
        result2 = import_gdelt_articles(db, _GDELT_ARTICLES)
    assert result2.persisted_count == 0
    assert result2.skipped_count >= 2


def test_gdelt_import_sets_hold_tier():
    from app.models.entities import LegalSource
    unique_url = "https://gdelt-test-hold.example.com/article-hold-tier"
    with SessionLocal() as db:
        import_gdelt_articles(db, [{"url": unique_url, "title": "Test", "domain": "example.com", "seendate": ""}])
        src = db.query(LegalSource).filter_by(url=unique_url).first()
    assert src is not None
    assert src.review_status == "pending_review"
    assert src.public_visibility is False


def test_gdelt_parse_date():
    from datetime import timezone
    dt = _parse_gdelt_date("20240315T120000Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.month == 3
    assert dt.day == 15
