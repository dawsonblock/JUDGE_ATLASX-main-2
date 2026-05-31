"""Tests for IngestionResult data structures and ADAPTER_REGISTRY completeness."""

from __future__ import annotations

import json
import pytest

from app.ingestion.adapters import (
    CreatedLegalInstrument,
    CreatedRecord,
    CreatedReviewItem,
    IngestionResult,
)
from app.ingestion.source_adapters import ADAPTER_REGISTRY
from app.ingestion.source_adapters.ckan_api import CKANApiAdapter
from app.ingestion.source_adapters.saskatoon_csv import SaskatoonCsvAdapter

# ── IngestionResult ──────────────────────────────────────────────────────────


class TestIngestionResult:
    def test_success_when_no_errors(self) -> None:
        result = IngestionResult(
            source_key="test",
            records_fetched=5,
            records_skipped=0,
            created_records=[],
            review_items=[],
            errors=[],
        )
        assert result.success is True

    def test_failure_when_errors_present(self) -> None:
        result = IngestionResult(
            source_key="test",
            records_fetched=0,
            records_skipped=0,
            created_records=[],
            review_items=[],
            errors=["Something went wrong"],
        )
        assert result.success is False

    def test_counts_consistent(self) -> None:
        records = [
            CreatedRecord(
                source_key="test",
                record_type="CrimeIncident",
                external_id="1",
                payload={},
            )
        ]
        result = IngestionResult(
            source_key="test",
            records_fetched=3,
            records_skipped=2,
            created_records=records,
            review_items=[],
            errors=[],
        )
        assert len(result.created_records) == 1
        assert result.records_skipped == 2

    def test_review_item_stored(self) -> None:
        item = CreatedReviewItem(
            source_key="test", headline=None, url=None, extracted_text=None
        )
        result = IngestionResult(
            source_key="test",
            records_fetched=1,
            records_skipped=0,
            created_records=[],
            review_items=[item],
            errors=[],
        )
        assert result.success is True
        assert len(result.review_items) == 1

    def test_legal_instrument_stored(self) -> None:
        item = CreatedLegalInstrument(
            source_key="test",
            instrument_type="Act",
            unique_id="C-46",
            language="eng",
            title="Criminal Code",
        )
        result = IngestionResult(
            source_key="test",
            records_fetched=1,
            legal_instruments=[item],
            errors=[],
        )
        assert result.success is True
        assert len(result.legal_instruments) == 1


# ── ADAPTER_REGISTRY completeness ────────────────────────────────────────────

EXPECTED_PARSER_KEYS = {
    "saskatoon_csv",
    "saskatoon_police_csv",
    "crawlee_police_release",
    "sk_courts_html",
    "statscan_table",
    "canlii_api",
    "federal_court_html",
    "scc_lexum_api",
    "crawlee_gov_news",
    "sk_legislature_html",
    "laws_justice_html",
    "laws_justice_xml",
    "ckan_api",
}


class TestAdapterRegistry:
    def test_all_expected_keys_present(self) -> None:
        missing = EXPECTED_PARSER_KEYS - set(ADAPTER_REGISTRY)
        assert not missing, f"Missing adapter keys: {missing}"

    def test_all_registered_adapters_have_run_method(self) -> None:
        for key, cls in ADAPTER_REGISTRY.items():
            assert hasattr(cls, "run"), f"Adapter {key} ({cls.__name__}) missing run()"

    def test_all_registered_adapters_have_fetch_method(self) -> None:
        for key, cls in ADAPTER_REGISTRY.items():
            assert hasattr(
                cls, "fetch"
            ), f"Adapter {key} ({cls.__name__}) missing fetch()"

    def test_all_registered_adapters_have_parse_method(self) -> None:
        for key, cls in ADAPTER_REGISTRY.items():
            assert hasattr(
                cls, "parse"
            ), f"Adapter {key} ({cls.__name__}) missing parse()"


# ── CKANApiAdapter unit checks ───────────────────────────────────────────────


class TestCKANApiAdapterUnit:
    def test_fetch_returns_empty_when_no_resource_id(self) -> None:
        adapter = CKANApiAdapter(
            source_key="test_ckan",
            base_url="https://opendata.saskatoon.ca",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
        )
        # No resource_id configured → fetch should return []
        rows = adapter.fetch()
        assert rows == []

    def test_parse_empty_rows_returns_empty(self) -> None:
        adapter = CKANApiAdapter(
            source_key="test_ckan",
            base_url="https://opendata.saskatoon.ca",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
        )
        parsed = adapter.parse([])
        assert parsed == []

    def test_parse_generates_stable_external_id_when_row_missing_identifier(self) -> None:
        adapter = CKANApiAdapter(
            source_key="test_ckan",
            base_url="https://opendata.saskatoon.ca",
            resource_id="rid",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
        )
        parsed = adapter.parse([{"field": "value", "lat": 52.13, "lon": -106.67}])
        assert len(parsed) == 1
        assert parsed[0].external_id is not None
        assert parsed[0].payload["coordinate_precision"] == "intersection"

    def test_run_creates_review_items_only(self) -> None:
        class _FetchResult:
            error = None
            raw_content = json.dumps(
                {
                    "success": True,
                    "result": {
                        "records": [{"_id": 1, "name": "row"}],
                        "total": 1,
                    },
                }
            ).encode("utf-8")
            http_status = 200
            content_type = "application/json"
            final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

        def _fetcher(url, allowed_domains, *, params=None, **kwargs):
            return _FetchResult()

        adapter = CKANApiAdapter(
            source_key="test_ckan",
            base_url="https://opendata.saskatoon.ca",
            resource_id="rid",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
            fetcher=_fetcher,
        )

        result = adapter.run()
        assert result.errors == []
        assert result.parser_version == "ckan_api_v1"
        assert result.created_records == []
        assert len(result.review_items) == 1
        assert result.raw_snapshot_bytes is not None
        assert result.fetch_http_status == 200

    def test_fetch_pages_results(self) -> None:
        class _FetchResult:
            def __init__(self, raw_content):
                self.error = None
                self.raw_content = raw_content
                self.http_status = 200
                self.content_type = "application/json"
                self.final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

        seen_offsets: list[int] = []

        def _fetcher(url, allowed_domains, *, params=None, **kwargs):
            offset = int((params or {}).get("offset", 0))
            seen_offsets.append(offset)
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
            source_key="test_ckan",
            base_url="https://opendata.saskatoon.ca",
            resource_id="rid",
            page_limit=2,
            max_pages=5,
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
            fetcher=_fetcher,
        )

        raw = adapter.fetch()
        assert len(raw) == 3
        assert seen_offsets == [0, 2]

    def test_run_preserves_rows_without_explicit_identifier(self) -> None:
        class _FetchResult:
            error = None
            raw_content = json.dumps(
                {
                    "success": True,
                    "result": {
                        "records": [{"name": "idless-row"}],
                        "total": 1,
                    },
                }
            ).encode("utf-8")
            http_status = 200
            content_type = "application/json"
            final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

        def _fetcher(url, allowed_domains, *, params=None, **kwargs):
            return _FetchResult()

        adapter = CKANApiAdapter(
            source_key="test_ckan",
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
        external_id = result.review_items[0].payload.get("external_id")
        assert isinstance(external_id, str)
        assert external_id.startswith("ckan-")


# ── SaskatoonCsvAdapter unit checks ─────────────────────────────────────────


class TestSaskatoonCsvAdapterUnit:
    def test_fetch_blocks_on_domain_violation(self) -> None:
        adapter = SaskatoonCsvAdapter(
            source_key="test_csv",
            base_url="https://malicious.example.com",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
        )
        rows = adapter.fetch()
        assert rows == []

    def test_parse_empty_rows_returns_empty(self) -> None:
        adapter = SaskatoonCsvAdapter(
            source_key="test_csv",
            base_url="https://opendata.saskatoon.ca",
            allowed_domains_json='["opendata.saskatoon.ca"]',
            public_record_authority="official_open_data",
        )
        parsed = adapter.parse([])
        assert parsed == []
