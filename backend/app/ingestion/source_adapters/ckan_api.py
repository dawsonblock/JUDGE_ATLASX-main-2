"""Adapter for CKAN Open Data portals (Canada Open Data, Saskatoon Open Data Portal).

Handles source keys: ``canada_open_data_crime``, ``saskatoon_open_data_portal``
Parser key: ``ckan_api``
Creates: varies — ``CrimeIncident`` for crime datasets, ``ReviewItem`` for others
Authority: ``official_statistics`` / ``official_open_data``

CKAN API docs: https://docs.ckan.org/en/stable/api/
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from typing import Any

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedReviewItem,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.schemas.ckan_crime_record import (
    build_ckan_review_payload,
    validate_ckan_row,
)
from app.ingestion.schemas.ckan_public_safety import build_ckan_public_safety_payload
from app.ingestion.source_keys import CANADA_OPEN_DATA_CRIME, SASKATOON_OPEN_DATA_PORTAL
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)


_RECORD_TYPE_MAP: dict[str, str] = {
    # Maps source_key prefix → default record type
    CANADA_OPEN_DATA_CRIME: "CrimeIncident",
    SASKATOON_OPEN_DATA_PORTAL: "ReviewItem",
}

_PARSER_VERSION = "ckan_api_v1"

_PUBLIC_SAFETY_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "saskatoon_open_data_public_safety",
    }
)


class CKANApiAdapter(CanadianSourceAdapter):
    """Fetch records from a CKAN-based open data portal.

    Both open.canada.ca and the Saskatoon Open Data Portal run CKAN.  This
    adapter uses the CKAN datastore API to download tabular data from a
    specific resource (identified by the resource ID embedded in ``base_url``
    or passed as ``resource_id``).

    For crime-statistic datasets the records are mapped to ``CrimeIncident``.
    For general civic datasets the records are mapped to ``ReviewItem``.

    .. note::
        The ``resource_id`` must be extracted from the ``base_url`` or
        ``SourceRegistry`` metadata before production use.
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        resource_id: str | None = None,
        page_limit: int = 100,
        max_pages: int = 10,
        offset: int = 0,
        allowed_domains_json: str | None = None,
        public_record_authority: str = "official_statistics",
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url.rstrip("/")
        self._resource_id = resource_id
        self._page_limit = max(1, min(page_limit, 100))
        self._max_pages = max(1, max_pages)
        self._offset = max(0, offset)
        self._allowed_domains_json = allowed_domains_json or "[]"
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._record_type = _RECORD_TYPE_MAP.get(source_key, "ReviewItem")
        self._fetcher = fetcher or fetch_for_ingestion
        self._raw_bytes: bytes | None = None
        self._raw_pages: list[dict[str, Any]] = []
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None
        self._last_fetch_error: str | None = None

    def _ckan_api_url(self) -> str:
        """Construct CKAN datastore_search API URL."""
        if self._resource_id:
            return (
                f"{self._base_url}/api/3/action/datastore_search"
                f"?resource_id={self._resource_id}&limit={self._page_limit}"
            )
        return f"{self._base_url}/api/3/action/datastore_search"

    def _build_params(self, offset: int) -> dict[str, Any]:
        return {
            "resource_id": self._resource_id,
            "limit": self._page_limit,
            "offset": offset,
        }

    def _classify_fetch_error(self, error: str) -> str:
        lowered = error.lower()
        if "allowlist" in lowered or "domain" in lowered:
            return "domain_not_allowed"
        if "ssrf" in lowered or "private" in lowered or "metadata" in lowered:
            return "ssrf_blocked"
        return "fetch_error"

    def _validate_row_schema(self, row: Any) -> bool:
        return validate_ckan_row(row)

    def _stable_external_id(self, row: dict[str, Any]) -> tuple[str, str, str]:
        resource_id = self._resource_id or "unknown_resource"
        explicit = row.get("_id") or row.get("id") or row.get("record_id") or row.get("uuid")
        if explicit is not None and str(explicit).strip():
            identity = f"{self._source_key}|{resource_id}|{str(explicit).strip()}"
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            return f"ckan-{digest[:24]}", "high", "official_record_id"

        event_date = str(
            row.get("event_date")
            or row.get("date")
            or row.get("occurrence_date")
            or ""
        ).strip()
        category = str(
            row.get("category")
            or row.get("incident_type")
            or row.get("type")
            or ""
        ).strip()
        location_text = str(
            row.get("location_text")
            or row.get("location")
            or row.get("address")
            or row.get("neighbourhood")
            or ""
        ).strip()
        fallback_identity = (
            f"{self._source_key}|{resource_id}|{event_date}|{category}|{location_text}"
        )
        digest = hashlib.sha256(fallback_identity.encode("utf-8")).hexdigest()
        return f"ckan-{digest[:24]}", "low", "composite_fallback"

    def _classify_coordinate_precision(self, row: dict[str, Any]) -> str:
        def _as_float(value: Any) -> float | None:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _decimal_places(value: Any) -> int:
            text = str(value)
            if "." not in text:
                return 0
            return len(text.rsplit(".", 1)[-1])

        lat_keys = ("latitude", "lat", "y")
        lon_keys = ("longitude", "lon", "lng", "x")
        lat_raw = next((row.get(key) for key in lat_keys if row.get(key) not in (None, "")), None)
        lon_raw = next((row.get(key) for key in lon_keys if row.get(key) not in (None, "")), None)

        lat = _as_float(lat_raw)
        lon = _as_float(lon_raw)
        if lat is None or lon is None:
            return "unknown"

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return "unknown"

        precision = min(_decimal_places(lat_raw), _decimal_places(lon_raw))
        if precision >= 4:
            return "exact"
        if precision == 3:
            return "block"
        if precision == 2:
            return "intersection"
        if precision == 1:
            return "neighbourhood"
        if precision == 0:
            return "city"
        return "unknown"

    def fetch(self) -> list[dict[str, Any]]:
        if not self._resource_id:
            self._last_fetch_error = "missing_resource_id"
            logger.warning("No resource_id configured for %s; cannot fetch data", self._source_key)
            return []

        api_url = self._ckan_api_url()
        rows: list[dict[str, Any]] = []
        offset = self._offset

        for _ in range(self._max_pages):
            params = self._build_params(offset)
            fetch_result = self._fetcher(api_url, self._allowed_domains, params=params)
            if fetch_result.error:
                reason = self._classify_fetch_error(fetch_result.error)
                self._last_fetch_error = reason
                logger.warning(
                    "CKAN fetch blocked for %s (%s): %s",
                    self._source_key,
                    reason,
                    fetch_result.error,
                )
                return []

            self._fetch_http_status = fetch_result.http_status
            self._fetch_content_type = fetch_result.content_type or "application/json"
            self._fetch_url = fetch_result.final_url or api_url
            if not fetch_result.raw_content:
                break

            try:
                payload = _json.loads(fetch_result.raw_content)
            except _json.JSONDecodeError:
                self._last_fetch_error = "invalid_json"
                logger.warning("CKAN payload for %s is not valid JSON", self._source_key)
                return []

            if not payload.get("success"):
                self._last_fetch_error = "ckan_unsuccessful_response"
                logger.warning("CKAN response reported success=false for %s", self._source_key)
                return []

            result_block = payload.get("result")
            if not isinstance(result_block, dict):
                self._last_fetch_error = "missing_result_block"
                logger.warning("CKAN response missing result block for %s", self._source_key)
                return []

            page_records = result_block.get("records")
            if not isinstance(page_records, list):
                self._last_fetch_error = "invalid_records_block"
                logger.warning("CKAN response has invalid records for %s", self._source_key)
                return []

            self._raw_pages.append(
                {
                    "offset": offset,
                    "limit": self._page_limit,
                    "record_count": len(page_records),
                    "payload": payload,
                }
            )

            validated = [row for row in page_records if self._validate_row_schema(row)]
            rows.extend(validated)

            total = result_block.get("total")
            if len(page_records) < self._page_limit:
                break
            if isinstance(total, int) and total <= offset + len(page_records):
                break
            offset += len(page_records)

        if self._raw_pages:
            snapshot = {
                "schema_version": "ckan_raw_snapshot_v1",
                "source_key": self._source_key,
                "parser_version": _PARSER_VERSION,
                "page_count": len(self._raw_pages),
                "pages": self._raw_pages,
            }
            self._raw_bytes = _json.dumps(snapshot, ensure_ascii=False).encode("utf-8")

        return rows

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        use_public_safety_schema = self._source_key in _PUBLIC_SAFETY_SOURCE_KEYS
        for row in raw:
            violation = check_record_type_allowed(
                self._record_type,
                self._public_record_authority,
                f'["{self._record_type}"]',
            )
            if violation:
                continue
            external_id, external_id_confidence, external_id_strategy = self._stable_external_id(row)
            coord_precision = self._classify_coordinate_precision(row)
            if use_public_safety_schema:
                payload = build_ckan_public_safety_payload(
                    source_key=self._source_key,
                    candidate_record_type=self._record_type,
                    external_id=external_id,
                    coordinate_precision=coord_precision,
                    raw=dict(row),
                    parser_version=_PARSER_VERSION,
                    public_record_authority=self._public_record_authority,
                    source_url=self._base_url,
                    external_id_confidence=external_id_confidence,
                    external_id_strategy=external_id_strategy,
                )
            else:
                payload = build_ckan_review_payload(
                    source_key=self._source_key,
                    candidate_record_type=self._record_type,
                    external_id=external_id,
                    coordinate_precision=coord_precision,
                    raw=dict(row),
                    parser_version=_PARSER_VERSION,
                    public_record_authority=self._public_record_authority,
                    source_url=self._base_url,
                    external_id_confidence=external_id_confidence,
                    external_id_strategy=external_id_strategy,
                )
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type="ReviewItem",
                    external_id=external_id,
                    payload=payload,
                    source_url=self._base_url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key)
        result.parser_version = _PARSER_VERSION
        try:
            if not self._resource_id:
                result.errors.append("missing_resource_id")
                return result

            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = self._raw_bytes
            result.fetch_http_status = self._fetch_http_status
            result.fetch_content_type = self._fetch_content_type
            result.fetch_url = self._fetch_url
            if self._last_fetch_error and not raw:
                result.errors.append(self._last_fetch_error)
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key,
                        headline=None,
                        url=p.source_url,
                        extracted_text=None,
                        confidence_score=0.0,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
