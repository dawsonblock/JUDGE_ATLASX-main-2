from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CrimeIncidentRecord:
    source_id: str | None
    external_id: str | None
    incident_type: str
    incident_category: str
    reported_at: datetime | None
    occurred_at: datetime | None
    city: str | None
    province_state: str | None
    country: str | None
    public_area_label: str | None
    latitude_public: float | None
    longitude_public: float | None
    precision_level: str
    source_url: str | None
    source_name: str
    verification_status: str
    data_last_seen_at: datetime | None
    is_public: bool
    notes: str | None = None
    is_aggregate: bool = False


@dataclass
class CrimeImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)

