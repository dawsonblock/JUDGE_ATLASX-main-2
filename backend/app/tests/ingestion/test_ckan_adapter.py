"""Ingestion-matrix CKAN tests (phase alignment wrapper).

These tests complement the top-level CKAN suite and keep a stable file path for
matrix-driven proof runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.schemas.ckan_public_safety import SCHEMA_VERSION as PUBLIC_SAFETY_SCHEMA_VERSION
from app.ingestion.source_adapters.ckan_api import CKANApiAdapter


def _fixture(name: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_ckan_pagination_fixture_pages_preserved() -> None:
    page1 = _fixture("saskatoon_public_safety_ckan_page1.json")
    page2 = _fixture("saskatoon_public_safety_ckan_page2.json")

    class _FetchResult:
        def __init__(self, payload: dict):
            self.error = None
            self.raw_content = json.dumps(payload).encode("utf-8")
            self.http_status = 200
            self.content_type = "application/json"
            self.final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        offset = int((params or {}).get("offset", 0))
        return _FetchResult(page1 if offset == 0 else page2)

    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="fixture-resource",
        page_limit=2,
        max_pages=3,
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.records_fetched == 3
    assert result.created_records == []
    assert len(result.review_items) == 3
    assert result.review_items[0].payload["schema_version"] == PUBLIC_SAFETY_SCHEMA_VERSION
    assert result.raw_snapshot_bytes is not None
