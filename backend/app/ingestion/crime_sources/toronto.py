"""Toronto Police Public Safety Data Portal adapter.

Imports CSV exports from https://data.torontopolice.on.ca/
into the standard CrimeIncidentRecord schema.

Publication policy is governed by SourceRegistry (source_key=toronto_crime).
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

SOURCE_NAME = "toronto_police"

_NEIGHBOURHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    "DOWNTOWN": (43.6532, -79.3832),
    "NORTH YORK": (43.7615, -79.4111),
    "SCARBOROUGH": (43.7764, -79.2318),
    "ETOBICOKE": (43.6205, -79.5132),
    "YORK": (43.6896, -79.4773),
    "EAST YORK": (43.6978, -79.3310),
    "UNKNOWN": (43.6532, -79.3832),
}


@dataclass
class TorontoImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def import_toronto_csv(
    db,
    file_like: io.StringIO | io.TextIOBase,
    commit: bool = True,
) -> TorontoImportResult:
    """Import Toronto Police CSV rows into CrimeIncident records.

    Expected columns: ``EVENT_UNIQUE_ID``, ``OCC_DATE``, ``MCI_CATEGORY``,
    ``OFFENCE``, ``NEIGHBOURHOOD_158``, ``LAT_WGS84``, ``LONG_WGS84``.
    """
    result = TorontoImportResult()
    reader = csv.DictReader(file_like)
    now = datetime.now(timezone.utc)

    for row_num, row in enumerate(reader, start=2):
        result.read_count += 1
        try:
            external_id = (row.get("EVENT_UNIQUE_ID") or "").strip()
            incident_type = (row.get("MCI_CATEGORY") or row.get("OFFENCE") or "").strip()
            neighbourhood = (row.get("NEIGHBOURHOOD_158") or "UNKNOWN").strip().upper()
            lat_str = (row.get("LAT_WGS84") or "").strip()
            lng_str = (row.get("LONG_WGS84") or "").strip()
            date_str = (row.get("OCC_DATE") or row.get("REPORT_DATE") or "").strip()

            if not incident_type:
                result.skipped_count += 1
                continue

            lat, lng = _resolve_coords(neighbourhood, lat_str, lng_str)
            if lat is None:
                result.skipped_count += 1
                result.errors.append(f"row {row_num}: no_coords")
                continue

            record = CrimeIncidentRecord(
                source_id=SOURCE_NAME,
                external_id=f"TPS-{external_id}" if external_id else None,
                incident_type=incident_type,
                incident_category=normalize_incident_category(
                    _category(incident_type)
                ),
                reported_at=_parse_dt(date_str) or now,
                occurred_at=_parse_dt(date_str),
                city="Toronto",
                province_state="ON",
                country="Canada",
                public_area_label=neighbourhood.title(),
                latitude_public=lat,
                longitude_public=lng,
                precision_level=normalize_precision_level("neighbourhood_centroid"),
                source_url="https://data.torontopolice.on.ca/",
                source_name=SOURCE_NAME,
                verification_status="reported",
                data_last_seen_at=now,
                is_public=False,
                is_aggregate=False,
                notes=None,
            )
            persist_crime_incident(db, record, source_key="toronto_crime")
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
    neighbourhood: str, lat_str: str, lng_str: str
) -> tuple[float | None, float | None]:
    try:
        return float(lat_str), float(lng_str)
    except (ValueError, TypeError):
        pass
    base = neighbourhood.split("(")[0].strip().upper()
    centroid = _NEIGHBOURHOOD_CENTROIDS.get(base)
    if centroid:
        return centroid
    return _NEIGHBOURHOOD_CENTROIDS.get("UNKNOWN") or (None, None)


def _parse_dt(value: str) -> datetime | None:
    for fmt in ("%Y/%m/%d %H:%M:%S+00", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:19], fmt[:len(value[:19])]).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


def _category(incident_type: str) -> str:
    t = incident_type.lower()
    if any(k in t for k in ("assault", "robbery", "shooting", "homicide", "sex")):
        return "violent"
    if any(k in t for k in ("theft", "break", "auto", "fraud")):
        return "property"
    return "other"
