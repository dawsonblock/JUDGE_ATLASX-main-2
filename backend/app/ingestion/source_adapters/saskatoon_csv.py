"""Adapter for Saskatoon Open Data crime incidents via ArcGIS GeoJSON.

Handles source key: ``saskatoon_open_data_crime``
Parser key: ``saskatoon_csv``
Creates: ``CrimeIncident`` records
Data source: https://opendata-saskatoon.opendata.arcgis.com/
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedRecord,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.external_id import make_external_id
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

_RECORD_TYPE = "CrimeIncident"

# Saskatoon city centroid — used when a feature lacks point geometry.
_CITY_LAT = 52.1332
_CITY_LON = -106.6700

# ArcGIS query parameters for a full GeoJSON export.
_ARCGIS_QUERY_PARAMS = {
    "outFields": "*",
    "where": "1=1",
    "f": "geojson",
    "returnGeometry": "true",
}

# Recognised property keys in priority order (ArcGIS schema may vary).
_COL_INCIDENT_TYPE = ("IncidentType", "incidenttype", "Offense_Type", "offense_type")
_COL_REPORTED_DATE = ("ReportedDate", "reporteddate", "Report_Date", "report_date")
_COL_NEIGHBOURHOOD = (
    "Neighbourhood",
    "neighbourhood",
    "Neighborhood",
    "Neighbrhd_Name",
)
_COL_OBJECTID = ("OBJECTID", "objectid", "FID")


def _pick_prop(props: dict[str, Any], candidates: tuple[str, ...]) -> str:
    for key in candidates:
        val = props.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _arcgis_url(base_url: str) -> str:
    """Ensure *base_url* ends with a GeoJSON query string."""
    parts = urlsplit(base_url)
    # If it already looks like a GeoJSON request, leave it alone.
    if "f=geojson" in (parts.query or ""):
        return base_url
    query = urlencode(_ARCGIS_QUERY_PARAMS)
    return urlunsplit(parts._replace(query=query))


class SaskatoonCsvAdapter(CanadianSourceAdapter):
    """Fetch Saskatoon Open Data crime incidents from the ArcGIS FeatureServer.

    The City of Saskatoon publishes crime data through an ArcGIS Open Data
    FeatureServer.  This adapter queries the GeoJSON endpoint, extracts point
    geometry (falling back to the city centroid when absent), and creates
    ``CrimeIncident`` records.

    The ``base_url`` should point to the FeatureServer query endpoint, e.g.::

        https://opendata-saskatoon.opendata.arcgis.com/datasets/<id>/FeatureServer/0/query

    If no query parameters are present, ``outFields=*&where=1=1&f=geojson`` is
    appended automatically.
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url
        self._allowed_domains_json = allowed_domains_json or "[]"
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        self._raw_bytes: bytes | None = None
        self._content_type: str = "application/geo+json"

    # ── SourceAdapter interface ──────────────────────────────────────────────

    def fetch(self) -> list[dict[str, Any]]:
        """Download GeoJSON from ArcGIS and return feature list."""
        import json as _json

        url = _arcgis_url(self._base_url)
        try:
            fetch_result = self._fetcher(url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "Domain check failed for %s: %s", self._source_key, fetch_result.error
                )
                return []
            self._raw_bytes = fetch_result.raw_content
            self._content_type = fetch_result.content_type or "application/geo+json"
            data = _json.loads(fetch_result.raw_content or b"{}")
            return data.get("features") or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", self._source_key, exc)
            return []

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        """Map GeoJSON features to ParsedRecord instances."""
        records: list[ParsedRecord] = []
        for feature in raw:
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                logger.warning("Record type gate failed: %s", violation.detail)
                continue

            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}

            # Extract lat/lon from Point geometry; fall back to city centroid.
            lat: float = _CITY_LAT
            lon: float = _CITY_LON
            precision = "city_centroid"
            if geom.get("type") == "Point":
                coords = geom.get("coordinates") or []
                if len(coords) >= 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    precision = "neighbourhood_centroid"

            incident_type = _pick_prop(props, _COL_INCIDENT_TYPE) or "unknown"
            reported_date = _pick_prop(props, _COL_REPORTED_DATE)
            neighbourhood = _pick_prop(props, _COL_NEIGHBOURHOOD)
            objectid = _pick_prop(props, _COL_OBJECTID)

            # Prefer OBJECTID as external_id; fall back to content hash.
            if objectid:
                external_id = make_external_id(self._source_key, objectid)
            else:
                external_id = make_external_id(
                    self._source_key,
                    hashlib.sha256(
                        f"{incident_type}:{reported_date}:{neighbourhood}:{lat}:{lon}".encode()
                    ).hexdigest(),
                )

            # Parse reported_at from date string if present.
            reported_at: datetime | None = None
            if reported_date:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        reported_at = datetime.strptime(reported_date, fmt).replace(
                            tzinfo=timezone.utc
                        )
                        break
                    except ValueError:
                        continue

            records.append(
                ParsedRecord(
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=external_id,
                    payload={
                        "incident_type": incident_type,
                        "incident_category": "crime",
                        "reported_at": (
                            reported_at.isoformat() if reported_at else reported_date
                        ),
                        "city": "Saskatoon",
                        "province_state": "Saskatchewan",
                        "country": "Canada",
                        "public_area_label": neighbourhood or None,
                        "latitude_public": lat,
                        "longitude_public": lon,
                        "precision_level": precision,
                        "source_key": self._source_key,
                        "source_url": self._base_url,
                        "verification_status": "reported",
                        "source_quality": "official_open_data",
                    },
                    source_url=self._base_url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key)
        try:
            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = self._raw_bytes
            result.content_type = self._content_type
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                result.created_records.append(
                    CreatedRecord(
                        source_key=p.source_key,
                        record_type=p.record_type,
                        external_id=p.external_id,
                        payload=p.payload,
                        source_url=p.source_url,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
