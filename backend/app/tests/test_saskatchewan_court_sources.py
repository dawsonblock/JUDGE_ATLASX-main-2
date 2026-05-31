"""Saskatchewan court source staging and adapter contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter


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


def _entry_for(source_key: str) -> dict:
    sources = _load_sources_yaml().get("sources", [])
    assert isinstance(sources, list)
    entry = next((s for s in sources if s.get("source_key") == source_key), None)
    assert entry is not None, f"missing source entry: {source_key}"
    return entry


def test_saskatchewan_court_sources_are_staged_disabled() -> None:
    for key in ("sk_courts_qb_decisions", "sk_courts_ca_decisions"):
        entry = _entry_for(key)
        assert entry["parser"] == "canlii_api"
        assert entry["source_class"] == "machine_ingest"
        assert entry["automation_status"] == "machine_ready_disabled"
        assert entry["enabled_default"] is False
        assert entry["requires_manual_review"] is True
        assert entry["public_publish_default"] is False


def test_canlii_adapter_fails_clearly_without_api_key() -> None:
    adapter = CanLIIApiAdapter(
        source_key="sk_courts_qb_decisions",
        base_url="https://api.canlii.org/v1",
        api_key=None,
        allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
        public_record_authority="official_court_record",
    )

    result = adapter.run()
    assert result.records_fetched == 0
    assert result.created_records == []
    assert result.review_items == []
    assert result.errors
    assert any("CANLII_API_KEY" in err for err in result.errors)


def test_canlii_adapter_fixture_run_is_review_only() -> None:
    payload = {
        "cases": [
            {
                "title": "Test v Saskatchewan",
                "url": "https://www.canlii.org/en/sk/skkb/doc/2026/2026skkb1/2026skkb1.html",
                "caseId": {"en": "2026SKKB1"},
                "decisionDate": "2026-01-01",
                "citation": "2026 SKKB 1",
            }
        ],
        "resultCount": 1,
    }

    class _FetchResult:
        error = None
        raw_content = json.dumps(payload).encode("utf-8")
        http_status = 200
        content_type = "application/json"
        final_url = "https://api.canlii.org/v1/caseBrowse/en/skkb/"

    def _fetcher(url, allowed_domains, *, params=None, **kwargs):
        return _FetchResult()

    adapter = CanLIIApiAdapter(
        source_key="sk_courts_qb_decisions",
        base_url="https://api.canlii.org/v1",
        api_key="fixture-key",
        allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
        public_record_authority="official_court_record",
        databases=["skkb"],
        fetcher=_fetcher,
    )

    result = adapter.run()
    assert result.errors == []
    assert result.parser_version == "1.0"
    assert result.created_records == []
    assert len(result.review_items) == 1
    assert result.review_items[0].payload["database_id"] == "skkb"
