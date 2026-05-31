# LEGACY: NOT_RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
# This file is quarantined from unconditional runtime loading.
# A reference copy lives in: legacy_disabled/us_ingestion_adapters/fbi_crime_data.py
# Do NOT import from app.ingestion.runner without the JTA_FBI_CRIME_ENABLED gate.
# ─────────────────────────────────────────────────────────────────────────────

"""FBI Crime Data API adapter.

Fetches agency-level offense counts from the FBI Crime Data Explorer API.
No API key is required for the public endpoints.

This source is TIER_AUTO (aggregate, no person names, no exact addresses).
Enable with JTA_FBI_CRIME_ENABLED=true.

Attribution: Federal Bureau of Investigation, Crime Data Explorer.
https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi
"""

from __future__ import annotations

# ruff: noqa: E402

# Sentinel: this adapter is quarantined from unconditional runtime loading.
# Standard ingestion scheduler must NOT import it without the env gate.
# Consumed by check_no_direct_ingestion_network_clients.py.
NOT_RUNTIME: bool = True

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from app.ingestion.crime_sources.base import CrimeIncidentRecord
from app.ingestion.crime_sources.persistence import (
    CrimeIncidentValidationError,
    normalize_incident_category,
    normalize_precision_level,
    persist_crime_incident,
)

log = logging.getLogger(__name__)

SOURCE_NAME = "fbi_crime_data"

_BASE_URL = "https://api.usa.gov/crime/fbi/cde"

_STATE_CENTROIDS: dict[str, tuple[float, float, str]] = {
    "AL": (32.3182, -86.9023, "Alabama"),
    "AK": (64.2008, -153.4937, "Alaska"),
    "AZ": (34.0489, -111.0937, "Arizona"),
    "AR": (34.7465, -92.2896, "Arkansas"),
    "CA": (36.7783, -119.4179, "California"),
    "CO": (39.5501, -105.7821, "Colorado"),
    "CT": (41.6032, -73.0877, "Connecticut"),
    "DE": (38.9108, -75.5277, "Delaware"),
    "FL": (27.6648, -81.5158, "Florida"),
    "GA": (32.1656, -82.9001, "Georgia"),
    "HI": (19.8968, -155.5828, "Hawaii"),
    "ID": (44.0682, -114.7420, "Idaho"),
    "IL": (40.6331, -89.3985, "Illinois"),
    "IN": (40.2672, -86.1349, "Indiana"),
    "IA": (41.8780, -93.0977, "Iowa"),
    "KS": (39.0119, -98.4842, "Kansas"),
    "KY": (37.8393, -84.2700, "Kentucky"),
    "LA": (30.9843, -91.9623, "Louisiana"),
    "ME": (45.2538, -69.4455, "Maine"),
    "MD": (39.0458, -76.6413, "Maryland"),
    "MA": (42.4072, -71.3824, "Massachusetts"),
    "MI": (44.3148, -85.6024, "Michigan"),
    "MN": (46.7296, -94.6859, "Minnesota"),
    "MS": (32.3547, -89.3985, "Mississippi"),
    "MO": (37.9643, -91.8318, "Missouri"),
    "MT": (46.8797, -110.3626, "Montana"),
    "NE": (41.4925, -99.9018, "Nebraska"),
    "NV": (38.8026, -116.4194, "Nevada"),
    "NH": (43.1939, -71.5724, "New Hampshire"),
    "NJ": (40.0583, -74.4057, "New Jersey"),
    "NM": (34.5199, -105.8701, "New Mexico"),
    "NY": (42.1657, -74.9481, "New York"),
    "NC": (35.7596, -79.0193, "North Carolina"),
    "ND": (47.5515, -101.0020, "North Dakota"),
    "OH": (40.4173, -82.9071, "Ohio"),
    "OK": (35.4676, -97.5164, "Oklahoma"),
    "OR": (43.8041, -120.5542, "Oregon"),
    "PA": (41.2033, -77.1945, "Pennsylvania"),
    "RI": (41.6809, -71.5118, "Rhode Island"),
    "SC": (33.8361, -81.1637, "South Carolina"),
    "SD": (43.9695, -99.9018, "South Dakota"),
    "TN": (35.5175, -86.5804, "Tennessee"),
    "TX": (31.9686, -99.9018, "Texas"),
    "UT": (39.3210, -111.0937, "Utah"),
    "VT": (44.5588, -72.5778, "Vermont"),
    "VA": (37.4316, -78.6569, "Virginia"),
    "WA": (47.7511, -120.7401, "Washington"),
    "WV": (38.5976, -80.4549, "West Virginia"),
    "WI": (43.7844, -88.7879, "Wisconsin"),
    "WY": (43.0760, -107.2903, "Wyoming"),
}


@dataclass
class FBIImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def import_fbi_json(db, payload: list[dict], commit: bool = True) -> FBIImportResult:
    """Import a list of FBI CDE offense-count dicts into CrimeIncident rows.

    Expected dict keys per item: ``state_abbr``, ``offense``, ``count``.
    """
    result = FBIImportResult()
    now = datetime.now(timezone.utc)

    for idx, item in enumerate(payload, start=1):
        result.read_count += 1
        try:
            state_abbr = (item.get("state_abbr") or "").strip().upper()
            offense = (item.get("offense") or item.get("offense_name") or "").strip()
            count = item.get("count") or item.get("actual") or 0

            if not state_abbr or not offense:
                result.skipped_count += 1
                continue

            state_info = _STATE_CENTROIDS.get(state_abbr)
            if state_info is None:
                result.skipped_count += 1
                continue

            lat, lng, state_name = state_info
            record = CrimeIncidentRecord(
                source_id=SOURCE_NAME,
                external_id=None,
                incident_type=offense,
                incident_category=normalize_incident_category(
                    _category_from_offense(offense)
                ),
                reported_at=now,
                occurred_at=None,
                city=None,
                province_state=state_abbr,
                country="United States",
                public_area_label=state_name,
                latitude_public=lat,
                longitude_public=lng,
                precision_level=normalize_precision_level("district_centroid"),
                source_url=f"{_BASE_URL}/offense/count/national/offense/{offense}",
                source_name=SOURCE_NAME,
                verification_status="aggregate_official",
                data_last_seen_at=now,
                is_public=False,
                is_aggregate=True,
                notes=f"Aggregate count: {count}. FBI Crime Data Explorer.",
            )
            persist_crime_incident(db, record, source_key="fbi_crime")
            result.persisted_count += 1
        except CrimeIncidentValidationError as exc:
            result.skipped_count += 1
            result.errors.append(f"item {idx}: skipped:{exc}")
        except Exception as exc:  # noqa: BLE001
            result.error_count += 1
            result.errors.append(f"item {idx}: error:{exc}")

    if commit:
        db.commit()
    return result


def fetch_fbi_offense_counts(
    state_abbr: str,
    offense: str = "aggravated-assault",
    client: httpx.Client | None = None,
) -> list[dict] | None:
    """Fetch offense counts for a state from the FBI CDE API.

    Returns a list of count dicts, or None on error.
    """
    url = f"{_BASE_URL}/offense/count/states/offense/{state_abbr}/{offense}"
    owns = client is None
    if owns:
        client = httpx.Client(timeout=20)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or data if isinstance(data, list) else []
        return [
            {
                "state_abbr": state_abbr,
                "offense": offense,
                "count": item.get("count", 0),
            }
            for item in items
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("FBI CDE fetch error (%s/%s): %s", state_abbr, offense, exc)
        return None
    finally:
        if owns:
            client.close()


def _category_from_offense(offense: str) -> str:
    o = offense.lower()
    if any(k in o for k in ("assault", "homicide", "robbery", "rape", "murder")):
        return "violent"
    if any(k in o for k in ("theft", "burglary", "larceny", "arson", "vandalism")):
        return "property"
    return "other"
