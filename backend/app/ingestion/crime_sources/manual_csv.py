import csv
from datetime import datetime, timezone
from io import StringIO
from typing import BinaryIO, TextIO

from sqlalchemy.orm import Session

from app.ingestion.crime_sources.base import CrimeImportResult, CrimeIncidentRecord
from app.ingestion.crime_sources.persistence import CrimeIncidentValidationError, normalize_incident_category, normalize_precision_level, persist_crime_incident

CSV_COLUMNS = [
    "source_id",
    "external_id",
    "incident_type",
    "incident_category",
    "reported_at",
    "occurred_at",
    "city",
    "province_state",
    "country",
    "public_area_label",
    "latitude_public",
    "longitude_public",
    "precision_level",
    "source_url",
    "source_name",
    "verification_status",
    "notes",
]


def import_crime_incidents_csv(db: Session, file_like: TextIO | BinaryIO | StringIO, commit: bool = True) -> CrimeImportResult:
    result = CrimeImportResult()
    reader = csv.DictReader(_text_stream(file_like))
    if not reader.fieldnames:
        result.error_count = 1
        result.errors.append("missing_header")
        return result

    missing = [column for column in CSV_COLUMNS if column not in reader.fieldnames]
    if missing:
        result.error_count = 1
        result.errors.append(f"missing_columns:{','.join(missing)}")
        return result

    for row_number, row in enumerate(reader, start=2):
        result.read_count += 1
        try:
            record = _record_from_row(row)
            persist_crime_incident(db, record)
            result.persisted_count += 1
        except CrimeIncidentValidationError as exc:
            result.skipped_count += 1
            result.errors.append(f"row {row_number}: skipped:{exc}")
        except Exception as exc:  # noqa: BLE001 - importer returns per-row failures
            result.error_count += 1
            result.errors.append(f"row {row_number}: error:{exc}")
    if commit:
        db.commit()
    return result


def _record_from_row(row: dict[str, str | None]) -> CrimeIncidentRecord:
    return CrimeIncidentRecord(
        source_id=_empty_to_none(row.get("source_id")),
        external_id=_empty_to_none(row.get("external_id")),
        incident_type=_required(row, "incident_type"),
        incident_category=normalize_incident_category(_required(row, "incident_category")),
        reported_at=_parse_datetime(row.get("reported_at")),
        occurred_at=_parse_datetime(row.get("occurred_at")),
        city=_empty_to_none(row.get("city")),
        province_state=_empty_to_none(row.get("province_state")),
        country=_empty_to_none(row.get("country")),
        public_area_label=_empty_to_none(row.get("public_area_label")),
        latitude_public=_parse_float(row.get("latitude_public")),
        longitude_public=_parse_float(row.get("longitude_public")),
        precision_level=normalize_precision_level(_required(row, "precision_level")),
        source_url=_empty_to_none(row.get("source_url")),
        source_name=_required(row, "source_name"),
        verification_status=_empty_to_none(row.get("verification_status")) or "reported",
        data_last_seen_at=datetime.now(timezone.utc),
        is_public=False,
        is_aggregate=False,
        notes=_empty_to_none(row.get("notes")),
    )


def _text_stream(file_like: TextIO | BinaryIO | StringIO) -> StringIO | TextIO:
    data = file_like.read()
    if isinstance(data, bytes):
        return StringIO(data.decode("utf-8-sig"))
    if isinstance(data, str):
        return StringIO(data)
    return file_like


def _parse_datetime(value: str | None) -> datetime | None:
    value = _empty_to_none(value)
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_float(value: str | None) -> float | None:
    value = _empty_to_none(value)
    return float(value) if value is not None else None


def _required(row: dict[str, str | None], key: str) -> str:
    value = _empty_to_none(row.get(key))
    if value is None:
        raise ValueError(f"missing_required:{key}")
    return value


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None

