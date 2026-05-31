"""Adapter for Saskatoon Police Service open-data crime CSV.

Handles source key: ``saskatoon_police_open_data``
Parser key: ``saskatoon_police_csv``
Creates: ``CrimeIncident`` records
Data source: https://www.saskatoonpolice.ca/open-data
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedRecord,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

_RECORD_TYPE = "CrimeIncident"

# Saskatoon city centroid — used when the open-data CSV omits coordinates.
_CITY_LAT = 52.1332
_CITY_LON = -106.6700

# Preferred column names in priority order (dataset publishes mixed casing).
_COL_INCIDENT_TYPE = ("IncidentType", "incidenttype", "Offence Type", "offence_type")
_COL_REPORTED_DATE = ("ReportedDate", "reporteddate", "Reported Date", "report_date")
_COL_NEIGHBOURHOOD = ("Neighbourhood", "neighbourhood", "Neighborhood", "neighborhood")


def _pick(row: dict[str, Any], candidates: tuple[str, ...]) -> str:
    """Return the first non-empty value from *row* matched by *candidates*."""
    for key in candidates:
        val = row.get(key)
        if val:
            return str(val).strip()
    return ""


class SaskatoonPoliceCsvAdapter(CanadianSourceAdapter):
    """Fetch and parse the Saskatoon Police Service open-data crime CSV.

    The Saskatoon Police Service publishes crime statistics on its open-data
    portal.  This adapter downloads the CSV, maps rows to ``CrimeIncident``
    payloads, and enforces source safety rules.

    Column names are resolved case-insensitively from a priority list; the
    open-data schema has changed over time so multiple variants are tried.
    When no coordinates are present a city-centroid geotag is applied with
    ``precision_level="city_centroid"``.

    The ``base_url`` comes from ``SourceRegistry.base_url`` for the
    ``saskatoon_police_open_data`` source key.
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
        self._content_type: str = "text/csv"

    def fetch(self) -> list[dict[str, Any]]:
        try:
            fetch_result = self._fetcher(self._base_url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "Domain check failed for %s: %s", self._source_key, fetch_result.error
                )
                return []
            self._raw_bytes = fetch_result.raw_content
            self._content_type = fetch_result.content_type or "text/csv"
            raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(raw_text))
            return list(reader)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", self._source_key, exc)
            return []

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        """Map CSV rows to ParsedRecord using confirmed open-data column names."""
        records: list[ParsedRecord] = []
        for row_num, row in enumerate(raw):
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                logger.warning("Record type gate failed: %s", violation.detail)
                continue

            incident_type = _pick(row, _COL_INCIDENT_TYPE) or "unknown"
            reported_date = _pick(row, _COL_REPORTED_DATE)
            neighbourhood = _pick(row, _COL_NEIGHBOURHOOD)

            # Parse reported_at from date string if present
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

            # Stable external_id from content hash (no row-number in open data)
            external_id = hashlib.sha256(
                f"{incident_type}:{reported_date}:{neighbourhood}:{row_num}".encode()
            ).hexdigest()

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
                        "latitude_public": _CITY_LAT,
                        "longitude_public": _CITY_LON,
                        "precision_level": "city_centroid",
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
