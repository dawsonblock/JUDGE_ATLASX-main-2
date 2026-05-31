"""CKAN public-safety adapter review-payload schema contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "ckan_public_safety_v1"


class CKANPublicSafetyReviewPayload(BaseModel):
    """Normalized review payload for staged CKAN public-safety datasets."""

    model_config = ConfigDict(extra="allow")

    source_key: str
    candidate_record_type: str
    external_id: str
    coordinate_precision: Literal[
        "exact",
        "block",
        "intersection",
        "neighbourhood",
        "city",
        "unknown",
    ]
    external_id_confidence: Literal["high", "low"] = "high"
    external_id_strategy: Literal["official_record_id", "composite_fallback"] = "official_record_id"
    raw: dict[str, Any]
    parser_version: str
    schema_version: str = SCHEMA_VERSION
    public_record_authority: str
    ingestion_mode: str = "review_only"
    source_url: str
    aggregate: bool = True
    record_scope: str = "aggregate_statistics_only"


def build_ckan_public_safety_payload(
    *,
    source_key: str,
    candidate_record_type: str,
    external_id: str,
    coordinate_precision: Literal[
        "exact",
        "block",
        "intersection",
        "neighbourhood",
        "city",
        "unknown",
    ],
    raw: dict[str, Any],
    parser_version: str,
    public_record_authority: str,
    source_url: str,
    external_id_confidence: Literal["high", "low"] = "high",
    external_id_strategy: Literal["official_record_id", "composite_fallback"] = "official_record_id",
) -> dict[str, Any]:
    """Build a validated review-only payload for CKAN public-safety rows."""
    payload = CKANPublicSafetyReviewPayload(
        source_key=source_key,
        candidate_record_type=candidate_record_type,
        external_id=external_id,
        coordinate_precision=coordinate_precision,
        external_id_confidence=external_id_confidence,
        external_id_strategy=external_id_strategy,
        raw=raw,
        parser_version=parser_version,
        public_record_authority=public_record_authority,
        source_url=source_url,
    )
    return payload.model_dump()
