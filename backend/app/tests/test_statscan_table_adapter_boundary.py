"""Boundary contract tests for StatscanTableAdapter.

Enforces the BOUNDARY: Statistics Canada sources must NOT produce records from
CSV data until the CSV parser integration is implemented.  These tests protect
against accidentally promoting statscan sources before the TODO in parse() is
resolved.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.ingestion.source_adapters.statscan_table import StatscanTableAdapter


def _make_fetch_result(
    raw_content: bytes | None,
    content_type: str = "application/octet-stream",
    error: str | None = None,
) -> MagicMock:
    result = MagicMock()
    result.raw_content = raw_content
    result.content_type = content_type
    result.error = error
    return result


def _make_adapter(fetcher: MagicMock | None = None) -> StatscanTableAdapter:
    return StatscanTableAdapter(
        source_key="statscan_ccjs_crime_sk_test",
        base_url="https://www150.statcan.gc.ca/t1/tbl1/en/dtbl!downloadTbl/csvDownload",
        public_record_authority="official_statistics",
        fetcher=fetcher or MagicMock(return_value=_make_fetch_result(b"", error="blocked")),
    )


# ---------------------------------------------------------------------------
# CSV boundary: rows with _raw_csv must NOT produce ParsedRecords
# ---------------------------------------------------------------------------


class TestCsvBoundary:
    def test_csv_raw_input_returns_empty_records(self) -> None:
        """parse() must skip CSV rows until CSV parser integration is done."""
        adapter = _make_adapter()
        raw = [{"_raw_csv": "GEO,REF_DATE,VALUE\nSaskatchewan,2023,1234\n"}]
        records = adapter.parse(raw)
        assert records == [], (
            "parse() must return [] for CSV input rows until the TODO is resolved"
        )

    def test_csv_boundary_does_not_silently_produce_data(self) -> None:
        """Calling run() with a CSV-returning fetcher must produce zero review items."""
        csv_bytes = b"GEO,REF_DATE,Statistics,UOM,VALUE\nSaskatchewan,2023,Crime rate,rate per 100k,5000\n"
        fetcher = MagicMock(
            return_value=_make_fetch_result(csv_bytes, content_type="text/csv")
        )
        adapter = _make_adapter(fetcher=fetcher)
        result = adapter.run()
        assert result.review_items == [], (
            "StatscanTableAdapter must not produce review items from CSV until "
            "BOUNDARY TODO is resolved"
        )

    def test_parse_empty_raw_returns_empty(self) -> None:
        adapter = _make_adapter()
        assert adapter.parse([]) == []


# ---------------------------------------------------------------------------
# Domain-blocked path
# ---------------------------------------------------------------------------


class TestDomainBlocked:
    def test_fetch_blocked_returns_empty(self) -> None:
        fetcher = MagicMock(
            return_value=_make_fetch_result(None, error="domain not in allowed list")
        )
        adapter = _make_adapter(fetcher=fetcher)
        assert adapter.fetch() == []

    def test_run_blocked_returns_no_errors_and_no_items(self) -> None:
        fetcher = MagicMock(
            return_value=_make_fetch_result(None, error="domain not in allowed list")
        )
        adapter = _make_adapter(fetcher=fetcher)
        result = adapter.run()
        assert result.review_items == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# JSON path (valid structured data)
# ---------------------------------------------------------------------------


class TestJsonPath:
    def test_json_list_rows_go_through_parse(self) -> None:
        """JSON rows that pass record-type check produce review items."""
        import json

        json_bytes = json.dumps(
            [{"REF_DATE": "2023", "GEO": "Saskatchewan", "Statistics": "Crime rate", "UOM": "rate"}]
        ).encode()
        fetcher = MagicMock(
            return_value=_make_fetch_result(json_bytes, content_type="application/json")
        )
        adapter = StatscanTableAdapter(
            source_key="statscan_test",
            base_url="https://www150.statcan.gc.ca/t1/tbl1/en/dtbl!downloadTbl/csvDownload",
            public_record_authority="official_statistics",
            fetcher=fetcher,
        )
        result = adapter.run()
        # If record-type rules pass, at least one item should be created
        # (this is a smoke test; actual rules are exercised via check_record_type_allowed)
        assert isinstance(result.review_items, list)
        assert result.errors == []
        assert result.parser_version == "statscan_table_v1"
        if result.review_items:
            payload = result.review_items[0].payload
            assert payload["aggregate"] is True
            assert payload["record_scope"] == "aggregate_statistics_only"
            assert payload["ingestion_mode"] == "review_only"
