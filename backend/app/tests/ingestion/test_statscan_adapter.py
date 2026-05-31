"""StatsCan adapter matrix tests.

Ensures StatsCan ingestion remains aggregate/review-only and does not emit
incident records.
"""

from __future__ import annotations

import json

from app.ingestion.schemas.statscan_aggregate_record import SCHEMA_VERSION
from app.ingestion.source_adapters.statscan_table import StatscanTableAdapter


def test_statscan_json_rows_produce_review_items_only() -> None:
    payload = [
        {
            "REF_DATE": "2025",
            "GEO": "Saskatchewan",
            "Statistics": "Crime rate",
            "UOM": "rate per 100,000",
            "VALUE": 5123,
        }
    ]

    class _FetchResult:
        error = None
        raw_content = json.dumps(payload).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl!downloadTbl/csvDownload"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _FetchResult()

    adapter = StatscanTableAdapter(
        source_key="statscan_ccjs_crime_sk",
        base_url="https://www150.statcan.gc.ca/t1/tbl1/en/dtbl!downloadTbl/csvDownload",
        public_record_authority="official_statistics",
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.created_records == []
    assert len(result.review_items) == 1
    payload = result.review_items[0].payload
    assert payload["aggregate"] is True
    assert payload["record_scope"] == "aggregate_statistics_only"
    assert payload["ingestion_mode"] == "review_only"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["aggregate_key"] == "2025_Saskatchewan_Crime rate_rate per 100,000"
