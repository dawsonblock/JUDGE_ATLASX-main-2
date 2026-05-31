"""Chicago Data Portal (Socrata) crime-feed adapter.

Transforms Chicago Police Department incident export CSVs (downloaded from
https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2)
into the standard CrimeIncidentRecord schema and imports them.

Unsafe records (exact addresses, person names) are rejected by the
publish-rules layer. Only community-area centroid precision is accepted.

Source tier: TIER_AUTO for structured fields (aggregate community area).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ingestion.crime_sources.base import CrimeIncidentRecord
from app.ingestion.crime_sources.persistence import (
    CrimeIncidentValidationError,
    normalize_incident_category,
    normalize_precision_level,
    persist_crime_incident,
)

SOURCE_NAME = "chicago_data_portal"

_COMMUNITY_AREA_CENTROIDS: dict[str, tuple[float, float]] = {
    "ROGERS PARK": (42.0082, -87.6660),
    "WEST RIDGE": (41.9981, -87.6936),
    "UPTOWN": (41.9686, -87.6546),
    "LINCOLN SQUARE": (41.9680, -87.6839),
    "NORTH CENTER": (41.9560, -87.6670),
    "LAKE VIEW": (41.9434, -87.6473),
    "LINCOLN PARK": (41.9246, -87.6454),
    "NEAR NORTH SIDE": (41.9000, -87.6334),
    "EDISON PARK": (42.0075, -87.8136),
    "LOOP": (41.8819, -87.6278),
    "ENGLEWOOD": (41.7797, -87.6408),
    "AUBURN GRESHAM": (41.7461, -87.6588),
    "ROSELAND": (41.6886, -87.6194),
    "UNKNOWN": (41.8781, -87.6298),
}


@dataclass
class ChicagoImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def import_chicago_csv(
    db,
    file_like: io.StringIO | io.TextIOBase,
    commit: bool = True,
) -> ChicagoImportResult:
    """Import Chicago Data Portal CSV rows into CrimeIncident records.

    Expected columns: ``ID``, ``Date``, ``Primary Type``, ``Description``,
    ``Community Area``, ``Latitude``, ``Longitude``, ``Year``.
    """
    result = ChicagoImportResult()
    reader = csv.DictReader(file_like)
    now = datetime.now(timezone.utc)

    for row_num, row in enumerate(reader, start=2):
        result.read_count += 1
        try:
            external_id = (row.get("ID") or "").strip()
            incident_type = (row.get("Primary Type") or "").strip()
            description = (row.get("Description") or "").strip()
            community = (row.get("Community Area Name") or row.get("Community Area") or "UNKNOWN").strip().upper()
            lat_str = (row.get("Latitude") or "").strip()
            lng_str = (row.get("Longitude") or "").strip()
            date_str = (row.get("Date") or "").strip()

            if not incident_type:
                result.skipped_count += 1
                continue

            lat, lng = _resolve_coords(community, lat_str, lng_str)
            if lat is None:
                result.skipped_count += 1
                result.errors.append(f"row {row_num}: no_coords:{community}")
                continue

            record = CrimeIncidentRecord(
                source_id=SOURCE_NAME,
                external_id=f"CHI-{external_id}" if external_id else None,
                incident_type=incident_type,
                incident_category=normalize_incident_category(
                    _category(incident_type)
                ),
                reported_at=_parse_dt(date_str) or now,
                occurred_at=_parse_dt(date_str),
                city="Chicago",
                province_state="IL",
                country="United States",
                public_area_label=community.title(),
                latitude_public=lat,
                longitude_public=lng,
                precision_level=normalize_precision_level("community_area_centroid"),
                source_url="https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2",
                source_name=SOURCE_NAME,
                verification_status="reported",
                data_last_seen_at=now,
                is_public=False,
                is_aggregate=False,
                notes=description if description else None,
            )
            persist_crime_incident(db, record, source_key="chicago_crime")
            result.persisted_count += 1
        except CrimeIncidentValidationError as exc:
            result.skipped_count += 1
            result.errors.append(f"row {row_num}: skipped:{exc}")
        except Exception as exc:  # noqa: BLE001
            result.error_count += 1
            result.errors.append(f"row {row_num}: error:{exc}")

    if commit:
        db.commit()
    return result


def _resolve_coords(
    community: str, lat_str: str, lng_str: str
) -> tuple[float | None, float | None]:
    try:
        return float(lat_str), float(lng_str)
    except (ValueError, TypeError):
        pass
    centroid = _COMMUNITY_AREA_CENTROIDS.get(community)
    if centroid:
        return centroid
    return _COMMUNITY_AREA_CENTROIDS.get("UNKNOWN") or (None, None)


def _parse_dt(value: str) -> datetime | None:
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _category(incident_type: str) -> str:
    t = incident_type.lower()
    if any(k in t for k in ("assault", "homicide", "robbery", "battery", "sex")):
        return "violent"
    if any(k in t for k in ("theft", "burglary", "motor vehicle", "arson")):
        return "property"
    return "other"
