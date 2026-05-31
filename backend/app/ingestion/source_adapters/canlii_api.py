"""Adapter for Saskatchewan Courts decisions via the CanLII API.

Handles source keys: ``sk_courts_qb_decisions``, ``sk_courts_ca_decisions``
(and any source using parser key ``canlii_api``)
Parser key: ``canlii_api``
Creates: ``ReviewItem`` records only
Authority: ``official_court_record``

CanLII API documentation: https://api.canlii.org/
API key required: Register at https://www.canlii.org/en/info/api.html

Without an API key, the adapter returns an empty result with a clear error
message rather than silently failing.

Database IDs for Saskatchewan courts:
- ``skkb`` — Saskatchewan Court of King's Bench
- ``skca`` — Saskatchewan Court of Appeal
- ``skpc`` — Saskatchewan Provincial Court

Evidence contract: every run() call that fetches data must set
    result.raw_snapshot_bytes, result.fetch_http_status,
    result.fetch_content_type, and result.fetch_url.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedReviewItem,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

_RECORD_TYPE = "ReviewItem"

# CanLII API base URL
_CANLII_API_BASE = "https://api.canlii.org/v1"

# Saskatchewan court database IDs
_SK_QB_DB = "skkb"
_SK_CA_DB = "skca"
_SK_PC_DB = "skpc"

# Default databases to query when no specific database is configured
_DEFAULT_SK_DATABASES = [_SK_QB_DB, _SK_CA_DB]
_PARSER_VERSION = "1.0"


class CanLIIApiAdapter(CanadianSourceAdapter):
    """Fetch Saskatchewan court decisions from the CanLII API.

    CanLII provides a REST API for searching and retrieving Canadian legal
    decisions.  This adapter queries the configured Saskatchewan court
    databases and creates ``ReviewItem`` records for each decision.

    All records require manual review before any judge/defendant associations
    are published.

    API key is required. Register at https://www.canlii.org/en/info/api.html
    and set ``CANLII_API_KEY`` in the environment, or pass via ``api_key``
    constructor argument.

    Configuration (via ``config_json`` in SourceRegistry):
    - ``databases``: list of CanLII database IDs to query (default: skkb, skca)
    - ``result_count``: max results per database (default: 100, max: 100)
    - ``offset``: pagination offset (default: 0)
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        api_key: str | None = None,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        databases: list[str] | None = None,
        result_count: int = 100,
        offset: int = 0,
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = (base_url or _CANLII_API_BASE).rstrip("/")
        self._api_key = api_key
        self._allowed_domains_json = (
            allowed_domains_json or '["api.canlii.org", "canlii.org"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._databases = databases or _DEFAULT_SK_DATABASES
        self._result_count = min(result_count, 100)  # API max is 100
        self._offset = offset
        self._fetcher = fetcher or fetch_for_ingestion
        # Evidence snapshot fields — populated during fetch().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _fetch_database(
        self, database_id: str
    ) -> tuple[list[dict[str, Any]], bytes | None, int | None, str | None, str | None]:
        """Fetch cases from a single CanLII database.

        Returns (cases, raw_bytes, http_status, content_type, fetch_url).
        """
        import json as _json

        url = f"{self._base_url}/caseBrowse/en/{database_id}/"
        params: dict[str, Any] = {
            "resultCount": self._result_count,
            "offset": self._offset,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            result = self._fetcher(url, self._allowed_domains, params=params)
            if result.error:
                logger.warning(
                    "Fetch blocked for %s (%s): %s",
                    self._source_key, database_id, result.error,
                )
                return [], None, None, None, None
            raw_bytes = result.raw_content
            http_status = result.http_status
            content_type = result.content_type or "application/json"
            fetch_url = result.final_url or url
            if not raw_bytes:
                return [], raw_bytes, http_status, content_type, fetch_url
            data = _json.loads(raw_bytes)
            cases = data.get("cases", [])
            logger.info(
                "CanLII %s/%s: fetched %d cases (total=%s)",
                self._source_key, database_id, len(cases),
                data.get("resultCount", "?"),
            )
            return cases, raw_bytes, http_status, content_type, fetch_url
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "CanLII fetch failed for %s/%s: %s",
                self._source_key, database_id, exc,
            )
            return [], None, None, None, None

    def fetch(self) -> list[dict[str, Any]]:
        if not self._api_key:
            logger.warning(
                "No CANLII_API_KEY configured for %s; returning empty result. "
                "Register at https://www.canlii.org/en/info/api.html",
                self._source_key,
            )
            return []

        results: list[dict[str, Any]] = []
        first_raw_bytes: bytes | None = None

        for db in self._databases:
            cases, raw_bytes, http_status, content_type, fetch_url = (
                self._fetch_database(db)
            )
                # Store evidence snapshot from first successful fetch.
            if raw_bytes and first_raw_bytes is None:
                first_raw_bytes = raw_bytes
                self._raw_bytes = raw_bytes
                self._fetch_http_status = http_status
                self._fetch_content_type = content_type
                self._fetch_url = fetch_url

            for case in cases:
                case["_db_id"] = db
                results.append(case)

        return results

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        for case in raw:
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                continue

            db_id = case.get("_db_id", "")
            case_id_obj = case.get("caseId", {})
            case_id = (
                case_id_obj.get("en") if isinstance(case_id_obj, dict) else case_id_obj
            )
            case_url = case.get("url") or (
                f"https://www.canlii.org/en/sk/{db_id}/doc/{case_id}/{case_id}.html"
                if case_id
                else ""
            )

            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=case_id or None,
                    payload={
                        "headline": case.get("title"),
                        "url": case_url,
                        "decision_date": case.get("decisionDate"),
                        "citation": case.get("citation"),
                        "database_id": db_id,
                        "case_id": case_id,
                    },
                    source_url=case_url or self._base_url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key)
        result.parser_version = _PARSER_VERSION
        try:
            if not self._api_key:
                result.errors.append(
                    "CANLII_API_KEY not configured. "
                    "Register at https://www.canlii.org/en/info/api.html "
                    "and set the CANLII_API_KEY environment variable."
                )
                return result

            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = self._raw_bytes
            result.fetch_http_status = self._fetch_http_status
            result.fetch_content_type = self._fetch_content_type
            result.fetch_url = self._fetch_url
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key,
                        headline=p.payload.get("headline"),
                        url=p.source_url,
                        extracted_text=p.payload.get("citation"),
                        confidence_score=0.9,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
