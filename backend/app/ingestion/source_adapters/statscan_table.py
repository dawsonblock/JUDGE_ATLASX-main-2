"""Adapter for Statistics Canada crime statistics tables.

Handles source keys: ``statscan_ccjs_crime_sk``, ``statscan_ucr_national``
Parser key: ``statscan_table``
Creates: ``ReviewItem`` records only
Authority: ``official_statistics``

Data source: https://www150.statcan.gc.ca/ (CANSIM / NDM tables)
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedReviewItem,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.schemas.statscan_aggregate_record import build_statscan_aggregate_payload
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

_RECORD_TYPE = "ReviewItem"
_PARSER_VERSION = "statscan_table_v1"

# Statistics Canada JSON API base for CANSIM table data
_STATSCAN_API_BASE = (
    "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl!downloadTbl/csvDownload"
)


class StatscanTableAdapter(CanadianSourceAdapter):
    """Fetch Statistics Canada CANSIM table data and produce review-only records.

    Statistics Canada publishes crime statistics through its CANSIM table
    service. This adapter fetches data as JSON or CSV (depending on the
    table's available formats) and maps aggregate rows to review-only payloads
    that are explicitly marked as aggregate statistics.

    .. note::
        Skeleton implementation.  The exact API endpoint and response schema
        must be verified against the live CANSIM API documentation.  Some
        tables require the product ID appended to the download URL.
        ``base_url`` from ``SourceRegistry`` should hold the full download URL
        for the specific table.
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
        self._allowed_domains_json = (
            allowed_domains_json or '["www150.statcan.gc.ca", "statcan.gc.ca"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        self._raw_bytes: bytes | None = None
        self._content_type: str = "application/octet-stream"

    def fetch(self) -> list[dict[str, Any]]:
        try:
            fetch_result = self._fetcher(self._base_url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "Domain check failed for %s: %s", self._source_key, fetch_result.error
                )
                return []
            # Attempt JSON parse; fall back to CSV stub
            self._raw_bytes = fetch_result.raw_content
            self._content_type = fetch_result.content_type or "application/octet-stream"
            try:
                data = _json.loads(fetch_result.raw_content or b"{}")
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "rows" in data:
                    return data["rows"]
                return [data]
            except Exception:
                # CSV fallback — return raw text for parse() to handle
                raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
                return [{"_raw_csv": raw_text}]
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", self._source_key, exc)
            return []

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        """Map Statistics Canada rows to CrimeIncident records.

        BOUNDARY: This method is INCOMPLETE. CSV rows are skipped (see below).
        Do not promote statscan sources to machine_ready_enabled until the TODO
        below is resolved and the CSV parser integration is implemented and tested.

        TODO: Replace placeholder field mapping with actual CANSIM schema
        column names for tables 35-10-0177-01 (CCJS) and 35-10-0069-01 (UCR).
        """
        records: list[ParsedRecord] = []
        for row in raw:
            if "_raw_csv" in row:
                # CSV not yet parsed — skip until CSV parsing is implemented
                logger.info(
                    "CSV data from %s requires CSV parser integration; skipping",
                    self._source_key,
                )
                continue
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                continue
            # Use a composite key as external_id for deduplication
            external_id = (
                "_".join(
                    str(row.get(k, ""))
                    for k in ("REF_DATE", "GEO", "Statistics", "UOM")
                )
                or None
            )
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=external_id,
                    payload=build_statscan_aggregate_payload(
                        source_key=self._source_key,
                        raw=dict(row),
                    ),
                    source_url=self._base_url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key)
        result.parser_version = _PARSER_VERSION
        try:
            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = self._raw_bytes
            result.content_type = self._content_type
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                ref_date = p.payload.get("raw", {}).get("REF_DATE", "")
                geo = p.payload.get("raw", {}).get("GEO", "")
                headline = (
                    f"Statistics Canada crime statistics: {geo} {ref_date}".strip(" :")
                )
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key,
                        headline=headline or None,
                        url=p.source_url,
                        extracted_text=str(p.payload.get("raw") or {}),
                        confidence_score=0.9,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
