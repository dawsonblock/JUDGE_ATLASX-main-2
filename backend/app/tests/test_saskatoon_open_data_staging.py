"""Fixture-backed staging tests for Saskatoon CKAN source entry."""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.source_adapters.ckan_api import CKANApiAdapter


def _load_sources_yaml() -> dict:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - environment guard
        raise AssertionError(f"PyYAML is required for this test: {exc}")

    source_file = (
        Path(__file__).resolve().parents[1]
        / "ingestion"
        / "sources"
        / "canada_saskatchewan_sources.yaml"
    )
    payload = yaml.safe_load(source_file.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_saskatoon_source_is_machine_ingest_runnable() -> None:
    data = _load_sources_yaml()
    sources = data.get("sources", [])
    assert isinstance(sources, list)

    entry = next(
        (s for s in sources if s.get("source_key") == "saskatoon_open_data_public_safety"),
        None,
    )
    assert entry is not None
    assert entry["parser"] == "ckan_api"
    assert entry["source_class"] == "machine_ingest"
    assert entry["automation_status"] == "machine_ready_enabled"
    assert entry["lifecycle_state"] == "runnable"
    assert entry["enabled_default"] is False


def test_saskatoon_fixture_path_exists() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[0]
        / "fixtures"
        / "saskatoon_open_data_crime_sample.json"
    )
    assert fixture_path.exists()


def test_saskatoon_ckan_fixture_runs_without_network() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[0]
        / "fixtures"
        / "saskatoon_open_data_crime_sample.json"
    )
    fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    class _FetchResult:
        error = None
        raw_content = json.dumps(fixture_payload).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://opendata.saskatoon.ca/api/3/action/datastore_search"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _FetchResult()

    adapter = CKANApiAdapter(
        source_key="saskatoon_open_data_public_safety",
        base_url="https://opendata.saskatoon.ca",
        resource_id="saskatoon-public-safety-fixture",
        allowed_domains_json='["opendata.saskatoon.ca"]',
        public_record_authority="official_open_data",
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.records_fetched == 2
    assert result.created_records == []
    assert len(result.review_items) == 2
    assert all(i.payload.get("ingestion_mode") == "review_only" for i in result.review_items)
