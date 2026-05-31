"""Tests: CrawleePoliceReleaseAdapter.run_with_db() Phase 2 implementation.

Verifies that run_with_db():
1. Constructs a WebMonitorTarget with source_type="police_news"
   and extractor_type="police_news_index".
2. Instantiates CrawleeRunner with the target and supplied db.
3. Awaits CrawleeRunner.run().
4. Returns runner.snapshots as a list.
5. Existing fetch() / parse() / run() stub behaviour is unaffected.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.source_adapters.crawlee_police_release import (
    CrawleePoliceReleaseAdapter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_adapter(
    source_key: str = "web_monitor_saskatoon_police_news",
    base_url: str = "https://www.saskatoonpolice.ca/news",
    allowed_domains_json: str = '["www.saskatoonpolice.ca"]',
) -> CrawleePoliceReleaseAdapter:
    return CrawleePoliceReleaseAdapter(
        source_key=source_key,
        base_url=base_url,
        allowed_domains_json=allowed_domains_json,
    )


def _run(coro):
    """Run a coroutine synchronously inside a test."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Phase 2 tests
# ---------------------------------------------------------------------------

class TestCrawleePoliceReleaseRunWithDb:
    def test_run_with_db_sets_police_news_source_type(self) -> None:
        """WebMonitorTarget gets source_type='police_news'."""
        adapter = _make_adapter()
        db = MagicMock()

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget"
        ) as MockTarget:
            MockTarget.return_value = MagicMock()
            _run(adapter.run_with_db(db))

        call_kwargs = MockTarget.call_args.kwargs
        assert call_kwargs["source_type"] == "police_news"

    def test_run_with_db_sets_police_news_index_extractor_type(self) -> None:
        """WebMonitorTarget gets extractor_type='police_news_index'."""
        adapter = _make_adapter()
        db = MagicMock()

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget"
        ) as MockTarget:
            MockTarget.return_value = MagicMock()
            _run(adapter.run_with_db(db))

        call_kwargs = MockTarget.call_args.kwargs
        assert call_kwargs["extractor_type"] == "police_news_index"

    def test_run_with_db_builds_target_with_source_key(self) -> None:
        """WebMonitorTarget receives the adapter's source_key."""
        adapter = _make_adapter(source_key="rcmp_sk_news")
        db = MagicMock()

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget"
        ) as MockTarget:
            MockTarget.return_value = MagicMock()
            _run(adapter.run_with_db(db))

        call_kwargs = MockTarget.call_args.kwargs
        assert call_kwargs["source_key"] == "rcmp_sk_news"

    def test_run_with_db_passes_db_to_runner(self) -> None:
        """CrawleeRunner receives the db session supplied to run_with_db."""
        adapter = _make_adapter()
        db = MagicMock()

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = []

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ) as MockRunner, patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            _run(adapter.run_with_db(db))

        _args, _kwargs = MockRunner.call_args
        assert _kwargs.get("db") is db or (_args and _args[1] is db)

    def test_run_with_db_awaits_runner_run(self) -> None:
        """CrawleeRunner.run() is awaited exactly once."""
        adapter = _make_adapter()
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

    def test_run_with_db_returns_snapshots(self) -> None:
        """run_with_db returns the list of snapshots from the runner."""
        adapter = _make_adapter()
        db = MagicMock()

        snap1, snap2 = MagicMock(), MagicMock()
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=None)
        mock_runner.snapshots = [snap1, snap2]

        with patch(
            "app.ingestion.source_adapters.crawlee_police_release.CrawleeRunner",
            return_value=mock_runner,
        ), patch(
            "app.ingestion.source_adapters.crawlee_police_release.WebMonitorTarget",
            return_value=MagicMock(),
        ):
            result = _run(adapter.run_with_db(db))

        assert result == [snap1, snap2]

    def test_run_with_db_works_for_rcmp_source_key(self) -> None:
        """run_with_db works for the rcmp_sk_news source key variant."""
        adapter = _make_adapter(
            source_key="rcmp_sk_news",
            base_url="https://www.rcmp-grc.gc.ca/en/news/sk",
            allowed_domains_json='["www.rcmp-grc.gc.ca"]',
        )
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

        assert result == []

    # ------------------------------------------------------------------
    # Regression: existing stub tests must still pass
    # ------------------------------------------------------------------

    def test_existing_fetch_still_raises_not_implemented(self) -> None:
        """Regression: fetch() still raises NotImplementedError (stub)."""
        adapter = _make_adapter()
        with pytest.raises(NotImplementedError):
            adapter.fetch()

    def test_existing_run_captures_error(self) -> None:
        """Regression: run() returns IngestionResult with error in errors list."""
        adapter = _make_adapter()
        result = adapter.run()
        assert len(result.errors) > 0
