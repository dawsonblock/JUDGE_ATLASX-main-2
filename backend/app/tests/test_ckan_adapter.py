"""Focused CKAN adapter hardening tests."""

from __future__ import annotations

import json

from app.ingestion.schemas.ckan_crime_record import SCHEMA_VERSION
from app.ingestion.source_adapters.ckan_api import CKANApiAdapter


def _make_fetch_result(payload: dict):
    class _FetchResult:
        error = None
        raw_content = json.dumps(payload).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://open.canada.ca/api/3/action/datastore_search"

    return _FetchResult()


def test_ckan_parse_payload_contains_schema_and_review_only_markers() -> None:
    adapter = CKANApiAdapter(
        source_key="canada_open_data_crime",
        base_url="https://open.canada.ca",
        resource_id="rid",
        allowed_domains_json='["open.canada.ca"]',
        public_record_authority="official_statistics",
    )

    parsed = adapter.parse([{"incident_type": "Theft", "lat": 52.1, "lon": -106.6}])

    assert len(parsed) == 1
    payload = parsed[0].payload
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["ingestion_mode"] == "review_only"
    assert payload["parser_version"] == "ckan_api_v1"
    assert payload["public_record_authority"] == "official_statistics"
    assert payload["candidate_record_type"] == "CrimeIncident"


def test_ckan_run_creates_review_items_not_incidents() -> None:
    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _make_fetch_result(
            {
                "success": True,
                "result": {
                    "records": [{"_id": 1, "incident_type": "Theft"}],
                    "total": 1,
                },
            }
        )

    adapter = CKANApiAdapter(
        source_key="canada_open_data_crime",
        base_url="https://open.canada.ca",
        resource_id="rid",
        allowed_domains_json='["open.canada.ca"]',
        public_record_authority="official_statistics",
        fetcher=_fetcher,
    )

    result = adapter.run()

    assert result.errors == []
    assert result.created_records == []
    assert len(result.review_items) == 1
    assert result.review_items[0].payload["ingestion_mode"] == "review_only"


def test_ckan_parse_generates_deterministic_external_id_without_explicit_id() -> None:
    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_portal",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
    )

    row = {"incident_type": "Assault", "year": 2024}
    parsed_first = adapter.parse([row])[0]
    parsed_second = adapter.parse([row])[0]

    assert parsed_first.external_id.startswith("ckan-")
    assert parsed_first.external_id == parsed_second.external_id
    assert parsed_first.payload["external_id_confidence"] == "low"
    assert parsed_first.payload["external_id_strategy"] == "composite_fallback"


def test_ckan_fetch_preserves_all_paginated_raw_pages_in_snapshot() -> None:
    class _FetchResult:
        def __init__(self, raw_content):
            self.error = None
            self.raw_content = raw_content
            self.http_status = 200
            self.content_type = "application/json"
            self.final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        offset = int((params or {}).get("offset", 0))
        if offset == 0:
            payload = {
                "success": True,
                "result": {
                    "records": [{"_id": 1}, {"_id": 2}],
                    "total": 3,
                },
            }
        else:
            payload = {
                "success": True,
                "result": {
                    "records": [{"_id": 3}],
                    "total": 3,
                },
            }
        return _FetchResult(json.dumps(payload).encode("utf-8"))

    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        page_limit=2,
        max_pages=5,
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.raw_snapshot_bytes is not None

    snapshot = json.loads(result.raw_snapshot_bytes.decode("utf-8"))
    assert snapshot["schema_version"] == "ckan_raw_snapshot_v1"
    assert snapshot["page_count"] == 2
    assert [page["offset"] for page in snapshot["pages"]] == [0, 2]


def test_ckan_fetch_rejects_malformed_rows_safely() -> None:
    class _FetchResult:
        error = None
        raw_content = json.dumps(
            {
                "success": True,
                "result": {
                    "records": [
                        {"_id": 1, "incident": "valid"},
                        {"_id": 2, "nested": {"bad": True}},
                        "not-a-dict",
                    ],
                    "total": 3,
                },
            }
        ).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _FetchResult()

    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.records_fetched == 1
    assert len(result.review_items) == 1


def test_ckan_coordinate_precision_taxonomy_is_normalized() -> None:
    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
    )

    parsed = adapter.parse(
        [
            {"_id": 1, "lat": "52.10001", "lon": "-106.60001"},
            {"_id": 2, "lat": "52.100", "lon": "-106.600"},
            {"_id": 3, "lat": "52.10", "lon": "-106.60"},
            {"_id": 4, "lat": "52.1", "lon": "-106.6"},
            {"_id": 5, "lat": "52", "lon": "-106"},
            {"_id": 6, "lat": "200", "lon": "-106"},
        ]
    )

    precisions = [item.payload["coordinate_precision"] for item in parsed]
    assert precisions == [
        "exact",
        "block",
        "intersection",
        "neighbourhood",
        "city",
        "unknown",
    ]


def test_ckan_explicit_identifier_is_hashed_and_marked_high_confidence() -> None:
    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
    )

    parsed = adapter.parse([{"_id": 12345, "lat": "52.1000", "lon": "-106.6000"}])[0]

    assert parsed.external_id.startswith("ckan-")
    assert "12345" not in parsed.external_id
    assert parsed.payload["external_id_confidence"] == "high"
    assert parsed.payload["external_id_strategy"] == "official_record_id"


def test_ckan_adapter_reports_expected_parser_version() -> None:
    class _FetchResult:
        error = None
        raw_content = json.dumps(
            {
                "success": True,
                "result": {"records": [{"_id": 1}], "total": 1},
            }
        ).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _FetchResult()

    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="rid",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
        fetcher=_fetcher,
    )
    result = adapter.run()
    assert result.parser_version == "ckan_api_v1"
