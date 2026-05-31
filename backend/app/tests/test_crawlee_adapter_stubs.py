"""Contract tests: CrawleeGovNewsAdapter and CrawleePoliceReleaseAdapter stub behaviour.

These tests enforce the adapter boundary: stubs MUST raise NotImplementedError from
fetch() and MUST NOT silently return data.  They also confirm that run() captures the
error into IngestionResult.errors rather than crashing the pipeline.
"""

from __future__ import annotations

import pytest

from app.ingestion.source_adapters.crawlee_gov_news import CrawleeGovNewsAdapter
from app.ingestion.source_adapters.crawlee_police_release import CrawleePoliceReleaseAdapter


# ---------------------------------------------------------------------------
# CrawleeGovNewsAdapter
# ---------------------------------------------------------------------------


class TestCrawleeGovNewsAdapterStub:
    def _make(self) -> CrawleeGovNewsAdapter:
        return CrawleeGovNewsAdapter(
            source_key="sk_gov_news_test",
            base_url="https://www.gov.sk.ca/news",
            allowed_domains_json='["www.gov.sk.ca"]',
        )

    def test_fetch_raises_not_implemented(self) -> None:
        adapter = self._make()
        with pytest.raises(NotImplementedError, match="stub"):
            adapter.fetch()

    def test_fetch_error_message_names_adapter(self) -> None:
        adapter = self._make()
        with pytest.raises(NotImplementedError) as exc_info:
            adapter.fetch()
        assert "CrawleeGovNewsAdapter" in str(exc_info.value)

    def test_run_captures_error_in_result(self) -> None:
        adapter = self._make()
        result = adapter.run()
        assert len(result.errors) == 1, "run() must capture stub error into errors list"
        assert "stub" in result.errors[0].lower() or "NotImplementedError" in result.errors[0]

    def test_run_returns_empty_records(self) -> None:
        adapter = self._make()
        result = adapter.run()
        assert result.review_items == []
        assert result.records_fetched == 0


# ---------------------------------------------------------------------------
# CrawleePoliceReleaseAdapter
# ---------------------------------------------------------------------------


class TestCrawleePoliceReleaseAdapterStub:
    def _make(self) -> CrawleePoliceReleaseAdapter:
        return CrawleePoliceReleaseAdapter(
            source_key="sk_police_news_test",
            base_url="https://saskatoonpolice.ca/news",
            allowed_domains_json='["saskatoonpolice.ca"]',
        )

    def test_fetch_raises_not_implemented(self) -> None:
        adapter = self._make()
        with pytest.raises(NotImplementedError, match="stub"):
            adapter.fetch()

    def test_fetch_error_message_names_adapter(self) -> None:
        adapter = self._make()
        with pytest.raises(NotImplementedError) as exc_info:
            adapter.fetch()
        assert "CrawleePoliceReleaseAdapter" in str(exc_info.value)

    def test_run_captures_error_in_result(self) -> None:
        adapter = self._make()
        result = adapter.run()
        assert len(result.errors) == 1, "run() must capture stub error into errors list"
        assert "stub" in result.errors[0].lower() or "NotImplementedError" in result.errors[0]

    def test_run_returns_empty_records(self) -> None:
        adapter = self._make()
        result = adapter.run()
        assert result.review_items == []
        assert result.records_fetched == 0
