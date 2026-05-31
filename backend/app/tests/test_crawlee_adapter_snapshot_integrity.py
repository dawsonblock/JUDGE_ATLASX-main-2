"""Tests: Snapshot and WebMonitorTarget integrity in crawlee adapter run_with_db().

Verifies that the WebMonitorTarget constructed inside run_with_db() carries the
correct structural data:
- source_key matches the adapter's configured key
- base_url is used as the crawl start point
- allowed_domains is parsed from allowed_domains_json (JSON array string)
- malformed allowed_domains_json falls back to an empty list (does not crash)
- name reflects the adapter identity

Covers both adapters to enforce the invariant uniformly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.ingestion.source_adapters.crawlee_gov_news import CrawleeGovNewsAdapter
from app.ingestion.source_adapters.crawlee_police_release import (
    CrawleePoliceReleaseAdapter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _run_gov_news(
    source_key="sk_justice_ministry",
    base_url="https://www.saskatchewan.ca/government/news",
    allowed_domains_json='["www.saskatchewan.ca"]',
):
    adapter = CrawleeGovNewsAdapter(
        source_key=source_key,
        base_url=base_url,
        allowed_domains_json=allowed_domains_json,
    )
    db = MagicMock()
    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=None)
    mock_runner.snapshots = []

    with patch(
        "app.ingestion.source_adapters.crawlee_gov_news.CrawleeRunner",
        return_value=mock_runner,
    ) as MockRunner, patch(
        "app.ingestion.source_adapters.crawlee_gov_news.WebMonitorTarget"
    ) as MockTarget:
        MockTarget.return_value = MagicMock()
        _run(adapter.run_with_db(db))
        return MockTarget, MockRunner

def _run_police(
    source_key="web_monitor_saskatoon_police_news",
    base_url="https://www.saskatoonpolice.ca/news",
    allowed_domains_json='["www.saskatoonpolice.ca"]',
):
    adapter = CrawleePoliceReleaseAdapter(
        source_key=source_key,
        base_url=base_url,
        allowed_domains_json=allowed_domains_json,
    )
    db = MagicMock()
    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=None)
    mock_runner.snapshots = []

    with patch(
        "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
        return_value=mock_runner,
    ) as MockRunner, patch(
        "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget"
    ) as MockTarget:
        MockTarget.return_value = MagicMock()
        _run(adapter.run_with_db(db))
        return MockTarget, MockRunner


# ---------------------------------------------------------------------------
# Snapshot integrity tests
# ---------------------------------------------------------------------------

class TestWebMonitorTargetSourceKey:
    def test_gov_news_source_key_passed_to_target(self) -> None:
        MockTarget, _ = _run_gov_news(source_key="sk_justice_ministry")
        assert MockTarget.call_args.kwargs["source_key"] == "sk_justice_ministry"

    def test_police_source_key_saskatoon(self) -> None:
        MockTarget, _ = _run_police(source_key="web_monitor_saskatoon_police_news")
        assert (
            MockTarget.call_args.kwargs["source_key"]
            == "web_monitor_saskatoon_police_news"
        )

    def test_police_source_key_rcmp(self) -> None:
        MockTarget, _ = _run_police(source_key="rcmp_sk_news")
        assert MockTarget.call_args.kwargs["source_key"] == "rcmp_sk_news"


class TestWebMonitorTargetBaseUrl:
    def test_gov_news_base_url_passed_to_target(self) -> None:
        url = "https://www.saskatchewan.ca/government/news"
        MockTarget, _ = _run_gov_news(base_url=url)
        assert MockTarget.call_args.kwargs["base_url"] == url

    def test_police_base_url_passed_to_target(self) -> None:
        url = "https://www.saskatoonpolice.ca/news"
        MockTarget, _ = _run_police(base_url=url)
        assert MockTarget.call_args.kwargs["base_url"] == url


class TestWebMonitorTargetAllowedDomains:
    def test_gov_news_allowed_domains_parsed_from_json(self) -> None:
        MockTarget, _ = _run_gov_news(
            allowed_domains_json='["www.saskatchewan.ca", "news.gov.sk.ca"]'
        )
        domains = MockTarget.call_args.kwargs["allowed_domains"]
        assert "www.saskatchewan.ca" in domains
        assert "news.gov.sk.ca" in domains

    def test_police_allowed_domains_parsed_from_json(self) -> None:
        MockTarget, _ = _run_police(
            allowed_domains_json='["www.saskatoonpolice.ca"]'
        )
        domains = MockTarget.call_args.kwargs["allowed_domains"]
        assert "www.saskatoonpolice.ca" in domains

    def test_gov_news_malformed_json_falls_back_to_empty_list(self) -> None:
        """Malformed JSON in allowed_domains_json must not raise; fallback is []."""
        MockTarget, _ = _run_gov_news(allowed_domains_json="NOT_VALID_JSON")
        domains = MockTarget.call_args.kwargs["allowed_domains"]
        assert isinstance(domains, list)
        assert domains == []

    def test_police_malformed_json_falls_back_to_empty_list(self) -> None:
        MockTarget, _ = _run_police(allowed_domains_json="{broken}")
        domains = MockTarget.call_args.kwargs["allowed_domains"]
        assert isinstance(domains, list)
        assert domains == []

    def test_empty_json_array_produces_empty_allowed_domains(self) -> None:
        MockTarget, _ = _run_gov_news(allowed_domains_json="[]")
        domains = MockTarget.call_args.kwargs["allowed_domains"]
        assert domains == []


class TestWebMonitorTargetName:
    def test_gov_news_name_contains_source_key(self) -> None:
        """Target name should identify the adapter/source for logging."""
        MockTarget, _ = _run_gov_news(source_key="sk_justice_ministry")
        name = MockTarget.call_args.kwargs.get("name", "")
        assert "sk_justice_ministry" in name or "SK Gov" in name

    def test_police_name_contains_source_key(self) -> None:
        MockTarget, _ = _run_police(source_key="rcmp_sk_news")
        name = MockTarget.call_args.kwargs.get("name", "")
        assert "rcmp_sk_news" in name or "Police" in name
