"""Tests for FederalCourtHtmlAdapter — offline, no network calls.

Tests cover:
- _parse_items(): h3/link parsing with fixture HTML
- parse(): ParsedRecord construction from raw dicts
- fetch(): domain blocking via a mock fetcher
- run(): full pipeline with a mock fetcher returning fixture HTML
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter

# ---------------------------------------------------------------------------
# Fixture HTML representing a single-page Federal Court decision index
# ---------------------------------------------------------------------------

_FIXTURE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Federal Court Decisions</title></head>
<body>
<h2>2 result(s)</h2>
<ul>
  <li>
    <a href="/fc-cf/decisions/en/item/12345/index.do">Smith v Canada</a>
    <h3>Smith v Canada-2025 FC 123-2025-03-15</h3>
  </li>
  <li>
    <a href="/fc-cf/decisions/en/item/67890/index.do">Jones v Minister</a>
    <h3>Jones v Minister-2025 FC 456-2025-04-01</h3>
  </li>
</ul>
</body>
</html>
"""

_FIXTURE_BYTES = _FIXTURE_HTML.encode()


def _make_fetch_result(
    raw_content: bytes | None = _FIXTURE_BYTES,
    error: str | None = None,
) -> MagicMock:
    """Return a MagicMock with the fetch-result fields the adapter reads."""
    result = MagicMock()
    result.raw_content = raw_content
    result.error = error
    return result


def _make_adapter(**kwargs: Any) -> FederalCourtHtmlAdapter:
    """Build an adapter with a no-network fetcher returning fixture HTML."""
    mock_fetcher = MagicMock(return_value=_make_fetch_result())
    return FederalCourtHtmlAdapter(
        source_key="federal_court_canada",
        base_url="https://decisions.fct-cf.gc.ca",
        public_record_authority="official_court_record",
        fetcher=mock_fetcher,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _parse_items — HTML parsing
# ---------------------------------------------------------------------------


class TestParseItems:
    def test_parses_two_decisions(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items(_FIXTURE_HTML)
        assert len(items) == 2

    def test_first_decision_url(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items(_FIXTURE_HTML)
        assert "12345" in items[0]["url"]

    def test_first_decision_citation(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items(_FIXTURE_HTML)
        assert items[0]["neutral_citation"] == "2025 FC 123"

    def test_first_decision_date(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items(_FIXTURE_HTML)
        assert items[0]["date"] == "2025-03-15"

    def test_second_decision_citation(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items(_FIXTURE_HTML)
        assert items[1]["neutral_citation"] == "2025 FC 456"

    def test_empty_html_returns_empty_list(self) -> None:
        adapter = _make_adapter()
        items = adapter._parse_items("<html><body></body></html>")
        assert items == []


# ---------------------------------------------------------------------------
# parse() — ParsedRecord construction
# ---------------------------------------------------------------------------


class TestParseParsedRecords:
    def _raw_items(self) -> list[dict[str, Any]]:
        return [
            {
                "url": "https://decisions.fct-cf.gc.ca/fc-cf/decisions/en/item/12345/index.do",
                "headline": "Smith v Canada",
                "neutral_citation": "2025 FC 123",
                "date": "2025-03-15",
            }
        ]

    def test_returns_one_parsed_record(self) -> None:
        adapter = _make_adapter()
        records = adapter.parse(self._raw_items())
        assert len(records) == 1

    def test_record_type_is_review_item(self) -> None:
        adapter = _make_adapter()
        records = adapter.parse(self._raw_items())
        assert records[0].record_type == "ReviewItem"

    def test_record_source_key(self) -> None:
        adapter = _make_adapter()
        records = adapter.parse(self._raw_items())
        assert records[0].source_key == "federal_court_canada"

    def test_record_payload_has_citation(self) -> None:
        adapter = _make_adapter()
        records = adapter.parse(self._raw_items())
        assert records[0].payload["neutral_citation"] == "2025 FC 123"

    def test_parse_empty_raw_returns_empty(self) -> None:
        adapter = _make_adapter()
        assert adapter.parse([]) == []


# ---------------------------------------------------------------------------
# run() — end-to-end with mock fetcher
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_returns_review_items(self) -> None:
        adapter = _make_adapter()
        result = adapter.run()
        assert len(result.review_items) == 2

    def test_run_no_errors(self) -> None:
        adapter = _make_adapter()
        result = adapter.run()
        assert result.errors == []

    def test_run_captures_raw_snapshot(self) -> None:
        adapter = _make_adapter()
        result = adapter.run()
        assert result.raw_snapshot_bytes == _FIXTURE_BYTES

    def test_run_captures_http_status(self) -> None:
        adapter = _make_adapter()
        result = adapter.run()
        assert result.fetch_http_status == 200


# ---------------------------------------------------------------------------
# Domain-blocked fetcher path
# ---------------------------------------------------------------------------


class TestDomainBlocked:
    def test_fetch_blocked_returns_empty(self) -> None:
        blocked_result = _make_fetch_result(raw_content=None, error="domain not in allowed list")
        adapter = FederalCourtHtmlAdapter(
            source_key="federal_court_canada",
            base_url="https://decisions.fct-cf.gc.ca",
            fetcher=MagicMock(return_value=blocked_result),
        )
        items = adapter.fetch()
        assert items == []
