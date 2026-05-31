"""Tests: Review-gate safety invariants for crawlee adapter run_with_db().

These tests verify the HARD SAFETY RULE:
  - CrawleeRunner.run() is always awaited (async call, never fire-and-forget).
  - snapshots returned by run_with_db are returned as a plain list (not an iterator
    or generator), ensuring callers can introspect them safely.
  - No auto-publish: run_with_db itself does not create ReviewItems — it only
    returns SourceSnapshot objects.  The extraction layer is responsible for
    enforcing PENDING + public_visibility=False when it creates ReviewItems.

Tested for both adapters to confirm the gate is adapter-agnostic.
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


def _gov_news_adapter() -> CrawleeGovNewsAdapter:
    return CrawleeGovNewsAdapter(
        source_key="sk_justice_ministry",
        base_url="https://www.saskatchewan.ca/government/news",
        allowed_domains_json='["www.saskatchewan.ca"]',
    )


def _police_adapter() -> CrawleePoliceReleaseAdapter:
    return CrawleePoliceReleaseAdapter(
        source_key="web_monitor_saskatoon_police_news",
        base_url="https://www.saskatoonpolice.ca/news",
        allowed_domains_json='["www.saskatoonpolice.ca"]',
    )


# ---------------------------------------------------------------------------
# Review-gate tests
# ---------------------------------------------------------------------------

class TestReviewGateAsync:
    """run_with_db() must be awaitable and must await the runner."""

    def test_run_with_db_is_coroutine_gov_news(self) -> None:
        """run_with_db on gov_news adapter returns a coroutine (is async)."""
        import inspect
        adapter = _gov_news_adapter()
        result = adapter.run_with_db(MagicMock())
        # Must be awaitable before we run it
        assert inspect.iscoroutine(result)
        # Clean up without running the loop
        result.close()

    def test_run_with_db_is_coroutine_police_release(self) -> None:
        """run_with_db on police_release adapter returns a coroutine (is async)."""
        import inspect
        adapter = _police_adapter()
        result = adapter.run_with_db(MagicMock())
        assert inspect.iscoroutine(result)
        result.close()

    def test_gov_news_awaits_runner_run_exactly_once(self) -> None:
        """Gov news adapter awaits CrawleeRunner.run() exactly once."""
        adapter = _gov_news_adapter()
        db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_gov_news.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_gov_news.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            _run(adapter.run_with_db(db))

        mock_runner.run.assert_awaited_once()

    def test_police_release_awaits_runner_run_exactly_once(self) -> None:
        """Police release adapter awaits CrawleeRunner.run() exactly once."""
        adapter = _police_adapter()
        db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            _run(adapter.run_with_db(db))

        mock_runner.run.assert_awaited_once()


class TestReviewGateNoAutoPublish:
    """run_with_db must NOT create ReviewItems directly — no auto-publish."""

    def test_gov_news_run_with_db_returns_list_not_review_items(self) -> None:
        """Gov news run_with_db returns SourceSnapshot list, NOT ReviewItems."""
        adapter = _gov_news_adapter()
        db = MagicMock()
        fake_snapshot = MagicMock(spec=["id", "source_key", "extracted_text"])
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = [fake_snapshot]

        with patch(
            "app.ingestion.source_adapters.crawlee_gov_news.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_gov_news.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            result = _run(adapter.run_with_db(db))

        assert isinstance(result, list)
        # db.add must NOT have been called with any ReviewItem
        for call_args in db.add.call_args_list:
            obj = call_args[0][0]
            assert type(obj).__name__ != "ReviewItem", (
                "run_with_db must not directly create ReviewItems"
            )

    def test_police_run_with_db_returns_list_not_review_items(self) -> None:
        """Police run_with_db returns SourceSnapshot list, NOT ReviewItems."""
        adapter = _police_adapter()
        db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            result = _run(adapter.run_with_db(db))

        assert isinstance(result, list)
        for call_args in db.add.call_args_list:
            obj = call_args[0][0]
            assert type(obj).__name__ != "ReviewItem"


class TestReviewGateReturnType:
    """Snapshots must be returned as a concrete list (not generator/iterator)."""

    def test_gov_news_result_is_plain_list(self) -> None:
        adapter = _gov_news_adapter()
        db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = [MagicMock(), MagicMock()]

        with patch(
            "app.ingestion.source_adapters.crawlee_gov_news.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_gov_news.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            result = _run(adapter.run_with_db(db))

        assert type(result) is list

    def test_police_result_is_plain_list(self) -> None:
        adapter = _police_adapter()
        db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = [MagicMock()]

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            result = _run(adapter.run_with_db(db))

        assert type(result) is list
