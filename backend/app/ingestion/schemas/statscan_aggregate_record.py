"""StatsCan aggregate statistics review-payload schema contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "statscan_aggregate_record_v1"


class StatscanAggregateReviewPayload(BaseModel):
    """Normalized review payload produced by the StatsCan table adapter."""

    model_config = ConfigDict(extra="allow")

    source_key: str
    aggregate: bool = True
    record_scope: str = "aggregate_statistics_only"
    ingestion_mode: str = "review_only"
    schema_version: str = SCHEMA_VERSION
    aggregate_key: str
    raw: dict[str, Any]


def build_statscan_aggregate_payload(*, source_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Build a validated review-only payload for aggregate statistics rows."""
    aggregate_key = "_".join(
        str(raw.get(key, "")) for key in ("REF_DATE", "GEO", "Statistics", "UOM")
    )
    payload = StatscanAggregateReviewPayload(
        source_key=source_key,
        aggregate_key=aggregate_key,
        raw=raw,
    )
    return payload.model_dump()
