"""Los Angeles Open Data crime dataset adapter.

Imports CSV exports from https://data.lacity.org/
into the standard CrimeIncidentRecord schema.

Source tier: TIER_AUTO for structured fields.
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

SOURCE_NAME = "los_angeles_open_data"

_AREA_CENTROIDS: dict[str, tuple[float, float]] = {
    "CENTRAL": (34.0510, -118.2500),
    "RAMPART": (34.0690, -118.2710),
    "SOUTHWEST": (34.0044, -118.3066),
    "HOLLENBECK": (34.0505, -118.1932),
    "HARBOR": (33.7975, -118.2781),
    "HOLLYWOOD": (34.0980, -118.3267),
    "WILSHIRE": (34.0636, -118.3510),
    "WEST LA": (34.0259, -118.4710),
    "VAN NUYS": (34.1866, -118.4488),
    "WEST VALLEY": (34.1966, -118.5680),
    "NORTHEAST": (34.1128, -118.2096),
    "77TH STREET": (33.9671, -118.2912),
    "NEWTON": (34.0156, -118.2612),
    "PACIFIC": (33.9803, -118.4508),
    "N HOLLYWOOD": (34.1866, -118.3963),
    "FOOTHILL": (34.2653, -118.3561),
    "DEVONSHIRE": (34.2584, -118.5143),
    "SOUTHEAST": (33.9389, -118.2353),
    "MISSION": (34.2788, -118.4430),
    "OLYMPIC": (34.0453, -118.3264),
    "TOPANGA": (34.1989, -118.6060),
    "UNKNOWN": (34.0522, -118.2437),
}


@dataclass
class LAImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def import_la_csv(
    db,
    file_like: io.StringIO | io.TextIOBase,
    commit: bool = True,
) -> LAImportResult:
    """Import LA Open Data crime CSV rows into CrimeIncident records.

    Expected columns: ``DR_NO``, ``DATE OCC``, ``Crm Cd Desc``,
    ``AREA NAME``, ``LAT``, ``LON``.
    """
    result = LAImportResult()
    reader = csv.DictReader(file_like)
    now = datetime.now(timezone.utc)

    for row_num, row in enumerate(reader, start=2):
        result.read_count += 1
        try:
            external_id = (row.get("DR_NO") or "").strip()
            incident_type = (row.get("Crm Cd Desc") or row.get("crm_cd_desc") or "").strip()
            area = (row.get("AREA NAME") or row.get("area_name") or "UNKNOWN").strip().upper()
            lat_str = (row.get("LAT") or row.get("lat") or "").strip()
            lng_str = (row.get("LON") or row.get("lon") or "").strip()
            date_str = (row.get("DATE OCC") or row.get("date_occ") or "").strip()

            if not incident_type:
                result.skipped_count += 1
                continue

            lat, lng = _resolve_coords(area, lat_str, lng_str)
            if lat is None:
                result.skipped_count += 1
                result.errors.append(f"row {row_num}: no_coords:{area}")
                continue

            record = CrimeIncidentRecord(
                source_id=SOURCE_NAME,
                external_id=f"LAPD-{external_id}" if external_id else None,
                incident_type=incident_type,
                incident_category=normalize_incident_category(
                    _category(incident_type)
                ),
                reported_at=_parse_dt(date_str) or now,
                occurred_at=_parse_dt(date_str),
                city="Los Angeles",
                province_state="CA",
                country="United States",
                public_area_label=area.title(),
                latitude_public=lat,
                longitude_public=lng,
                precision_level=normalize_precision_level("district_centroid"),
                source_url="https://data.lacity.org/",
                source_name=SOURCE_NAME,
                verification_status="reported",
                data_last_seen_at=now,
                is_public=False,
                is_aggregate=False,
                notes=None,
            )
            persist_crime_incident(db, record, source_key="la_crime")
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
    area: str, lat_str: str, lng_str: str
) -> tuple[float | None, float | None]:
    try:
        lat, lng = float(lat_str), float(lng_str)
        if lat == 0.0 or lng == 0.0:
            raise ValueError("zero coords")
        return lat, lng
    except (ValueError, TypeError):
        pass
    centroid = _AREA_CENTROIDS.get(area)
    if centroid:
        return centroid
    return _AREA_CENTROIDS.get("UNKNOWN") or (None, None)


def _parse_dt(value: str) -> datetime | None:
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _category(incident_type: str) -> str:
    t = incident_type.lower()
    if any(k in t for k in ("assault", "robbery", "homicide", "rape", "weapon")):
        return "violent"
    if any(k in t for k in ("theft", "burglary", "vandalism", "arson", "fraud")):
        return "property"
    return "other"
