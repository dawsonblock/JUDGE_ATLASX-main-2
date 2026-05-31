"""Statistics Canada crime data adapter.

Fetches Table 35-10-0177-01 (Incident-based crime statistics) from the
Statistics Canada public CSV download endpoint and maps aggregate rows to
CrimeIncidentRecord objects.

Publication policy is governed by SourceRegistry (source_key=statscan);
default is TIER_HOLD pending manual review. Enable with JTA_STATSCAN_ENABLED=true.

Attribution: Statistics Canada. Table 35-10-0177-01.
https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/35100177
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile
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

SOURCE_NAME = "statistics_canada"

_DEFAULT_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/35100177/35100177.zip"

_PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Alberta": (53.9333, -116.5765),
    "British Columbia": (53.7267, -127.6476),
    "Manitoba": (56.4150, -98.7390),
    "New Brunswick": (46.5653, -66.4619),
    "Newfoundland and Labrador": (53.1355, -57.6604),
    "Northwest Territories": (64.8255, -124.8457),
    "Nova Scotia": (44.6820, -63.7443),
    "Nunavut": (70.2998, -83.1076),
    "Ontario": (51.2538, -85.3232),
    "Prince Edward Island": (46.5107, -63.4168),
    "Quebec": (52.9399, -73.5491),
    "Saskatchewan": (52.9399, -106.4509),
    "Yukon": (64.2823, -135.0000),
    "Canada": (56.1304, -106.3468),
}


@dataclass
class StatCanImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


_ZIP_MAGIC = b"PK\x03\x04"


def import_statscan_csv(
    db,
    file_like: io.StringIO | io.TextIOBase | io.RawIOBase | io.BufferedIOBase,
    commit: bool = True,
) -> StatCanImportResult:
    """Import a Statistics Canada CSV stream into CrimeIncident rows.

    Expects the standard 35-10-0177-01 column layout.
    Publication tier is determined by SourceRegistry; records default to pending_review.

    Raises ValueError if a ZIP archive is passed instead of a plain CSV.
    StatsCan distributes data as a ZIP; callers must extract the CSV first.
    """
    # Read all content upfront: compute batch hash and perform ZIP guard in one pass.
    # Gate 0b in auto_review() requires has_snapshot_hash=True for non-reference sources.
    if isinstance(file_like, (io.RawIOBase, io.BufferedIOBase)):
        raw_bytes = file_like.read()
        if raw_bytes[:4] == _ZIP_MAGIC:
            raise ValueError(
                "StatsCan upload appears to be a ZIP archive. "
                "Extract the CSV from the ZIP before calling import_statscan_csv."
            )
        batch_hash = hashlib.sha256(raw_bytes).hexdigest()
        content_str = raw_bytes.decode("utf-8", errors="replace")
    else:
        # StringIO or generic TextIOBase
        content_str = file_like.read()
        if content_str.encode("latin-1", errors="replace")[:4] == _ZIP_MAGIC:
            raise ValueError(
                "StatsCan upload appears to be a ZIP archive. "
                "Extract the CSV from the ZIP before calling import_statscan_csv."
            )
        batch_hash = hashlib.sha256(
            content_str.encode("utf-8", errors="replace")
        ).hexdigest()

    result = StatCanImportResult()
    reader = csv.DictReader(io.StringIO(content_str))
    now = datetime.now(timezone.utc)

    for row_num, row in enumerate(reader, start=2):
        result.read_count += 1
        try:
            geography = (row.get("GEO") or "").strip()
            violation = (row.get("Violations") or row.get("violation") or "").strip()
            value_str = (row.get("VALUE") or row.get("value") or "0").strip()

            if not geography or not violation:
                result.skipped_count += 1
                continue

            coords = _province_coords(geography)
            if coords is None:
                result.skipped_count += 1
                continue

            lat, lng = coords
            ext_id = (
                "SC-"
                + hashlib.sha256(f"{geography}|{violation}".encode())
                .hexdigest()[:16]
                .upper()
            )
            record = CrimeIncidentRecord(
                source_id=SOURCE_NAME,
                external_id=ext_id,
                incident_type=violation,
                incident_category=normalize_incident_category(
                    _category_from_violation(violation)
                ),
                reported_at=now,
                occurred_at=None,
                city=None,
                province_state=geography,
                country="Canada",
                public_area_label=geography,
                latitude_public=lat,
                longitude_public=lng,
                precision_level=normalize_precision_level("province_centroid"),
                source_url="https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/35100177",
                source_name=SOURCE_NAME,
                verification_status="aggregate_official",
                data_last_seen_at=now,
                is_public=False,
                is_aggregate=True,
                notes=f"Aggregate count: {value_str}. Statistics Canada Table 35-10-0177-01.",
            )
            persist_crime_incident(
                db, record, source_key="statscan", import_batch_hash=batch_hash
            )
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


def extract_csv_from_bytes(content: bytes) -> str | None:
    """Extract CSV text from raw bytes.

    If *content* starts with the ZIP magic bytes (``PK\\x03\\x04``) the
    first CSV entry (alphabetically) is extracted and decoded with
    ``utf-8-sig`` (strips BOM) falling back to ``latin-1``.

    Plain-text bytes are decoded with ``utf-8-sig``.
    Returns ``None`` if the ZIP contains no CSV files.
    """
    if content[:4] == _ZIP_MAGIC:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_names = sorted(
                name for name in zf.namelist() if name.lower().endswith(".csv")
            )
            if not csv_names:
                log.warning("StatsCan ZIP contained no CSV files")
                return None
            raw_bytes = zf.read(csv_names[0])
            try:
                return raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                return raw_bytes.decode("latin-1")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def extract_csv_from_response(resp: "httpx.Response") -> str | None:
    """Extract CSV text from an httpx response.

    Delegates to :func:`extract_csv_from_bytes` for ZIP/plain-text handling.
    Returns ``None`` if the ZIP contains no CSV files.
    """
    return extract_csv_from_bytes(resp.content)


def fetch_statscan_csv(client: httpx.Client | None = None) -> str | None:
    """Fetch the Statistics Canada CSV. Returns CSV text or None on error.

    The official download endpoint serves a ZIP archive; this function
    automatically extracts the first CSV from the ZIP via
    :func:`extract_csv_from_response`.
    """
    owns = client is None
    if owns:
        client = httpx.Client(timeout=30)
    try:
        resp = client.get(_DEFAULT_URL)
        resp.raise_for_status()
        return extract_csv_from_response(resp)
    except Exception as exc:  # noqa: BLE001
        log.warning("StatsCan fetch error: %s", exc)
        return None
    finally:
        if owns:
            client.close()


def _province_coords(geography: str) -> tuple[float, float] | None:
    return _PROVINCE_CENTROIDS.get(geography)


def _category_from_violation(violation: str) -> str:
    v = violation.lower()
    if any(k in v for k in ("assault", "homicide", "robbery", "sexual")):
        return "violent"
    if any(k in v for k in ("theft", "fraud", "break", "mischief", "property")):
        return "property"
    return "other"
