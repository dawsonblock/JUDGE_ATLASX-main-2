"""Adapter for Federal Court of Canada HTML decision pages.

Handles source key: ``federal_court_canada``
Parser key: ``federal_court_html``
Creates: ``ReviewItem`` records only
Authority: ``official_court_record``

Validated against live site (2026-05-06):
- Recent decisions (last 100): ``https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true``
- Year-based navigation: ``/fc-cf/decisions/en/{year}/nav_date.do?iframe=true&page={page}``
  - 24 items per page; total shown in ``<h2>N result(s)</h2>``
  - Year links available from 1972 to present
- Decision links: ``<a href="/fc-cf/decisions/en/item/NNNNN/index.do">``
- Each ``<h3>`` contains: ``CaseName-NeutralCitation-Date``
- English decisions use ``/en/item/``, French use ``/fr/item/``

Evidence contract: every run() call that fetches data must set
    result.raw_snapshot_bytes, result.fetch_http_status,
    result.fetch_content_type, and result.fetch_url.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedReviewItem,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

_RECORD_TYPE = "ReviewItem"

_FC_BASE = "https://decisions.fct-cf.gc.ca"

# Recent decisions iframe URL (last 100 results, no pagination needed)
_FC_RECENT_URL = _FC_BASE + "/fc-cf/en/0/ann.do?iframe=true"

# Year-based navigation URL template
_FC_YEAR_URL = _FC_BASE + "/fc-cf/decisions/en/{year}/nav_date.do?iframe=true&page={page}"

# Regex to parse the h3 title: "CaseName-NeutralCitation-Date"
_H3_PATTERN = re.compile(
    r"^(?P<case_name>.+?)-(?P<citation>\d{4}\s+(?:FC|CF)\s+\d+)-(?P<date>\d{4}-\d{2}-\d{2})$"
)

# Items per page on the year-navigation endpoint
_ITEMS_PER_PAGE = 25

# Must match parser_version in canada_saskatchewan_sources.yaml (federal_court_canada entry)
PARSER_VERSION = "1.0"


def _parse_total(soup: BeautifulSoup) -> int | None:
    """Extract total result count from h2 element."""
    h2 = soup.find("h2")
    if h2:
        m = re.search(r"(\d+)\s+result", h2.get_text(strip=True))
        if m:
            return int(m.group(1))
    return None


class FederalCourtHtmlAdapter(CanadianSourceAdapter):
    """Scrape Federal Court of Canada decision index for ReviewItem candidates.

    Supports two fetch modes:
    1. **Recent** (default): fetches the last 100 decisions from the iframe endpoint.
    2. **Year-based**: fetches all decisions for a given year using paginated
       navigation (``/fc-cf/decisions/en/{year}/nav_date.do``).

    Set ``config_json`` in the source registry to ``{"year": 2025}`` to fetch
    a specific year's decisions. Omit to use recent-only mode.

    All records require manual review (``requires_manual_review: true``).
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        year: int | None = None,
        limit: int | None = None,
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url
        self._allowed_domains_json = (
            allowed_domains_json or '["decisions.fct-cf.gc.ca", "fct-cf.gc.ca", "www.fct-cf.gc.ca"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._year = year
        self._limit = limit  # max items to fetch (None = all)
        self._fetcher = fetcher or fetch_for_ingestion
        # Evidence snapshot fields — populated during fetch().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _parse_items(self, html: str) -> list[dict[str, Any]]:
        """Extract English decision entries from a Federal Court page.

        Looks for ``<a href="/fc-cf/decisions/en/item/NNNNN/index.do">`` links
        and pairs them with the sibling ``<h3>`` heading for metadata.
        """
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []

        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if "/decisions/en/item/" not in href:
                continue
            full_url = href if href.startswith("http") else _FC_BASE + href
            headline = link.get_text(strip=True)
            if not headline:
                continue

            neutral_citation: str | None = None
            date: str | None = None
            h3 = link.find_parent("h3") or link.find_next("h3")
            if h3:
                h3_text = h3.get_text(strip=True)
                m = _H3_PATTERN.match(h3_text)
                if m:
                    neutral_citation = m.group("citation")
                    date = m.group("date")

            items.append(
                {
                    "url": full_url,
                    "headline": headline,
                    "neutral_citation": neutral_citation,
                    "date": date,
                }
            )
        return items

    def _fetch_url_content(self, url: str) -> bytes | None:
        """Fetch a URL and return raw bytes, or None on failure."""
        try:
            result = self._fetcher(url, self._allowed_domains)
            if result.error:
                logger.warning("Domain blocked for %s: %s", self._source_key, result.error)
                return None
            return result.raw_content
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", url, exc)
            return None

    def fetch(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        if self._year:
            # Year-based paginated fetch
            page = 1
            while True:
                url = _FC_YEAR_URL.format(year=self._year, page=page)
                content = self._fetch_url_content(url)
                if content is None:
                    break

                # Store raw bytes from first page as the evidence snapshot.
                if page == 1:
                    self._raw_bytes = content
                    self._fetch_http_status = 200
                    self._fetch_content_type = "text/html"
                    self._fetch_url = url

                html = content.decode("utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                page_items = self._parse_items(html)

                if not page_items:
                    break

                all_items.extend(page_items)

                # Check if we've hit the limit
                if self._limit and len(all_items) >= self._limit:
                    all_items = all_items[: self._limit]
                    break

                # Check if there are more pages
                total = _parse_total(soup)
                if total is None or len(all_items) >= total:
                    break

                # Check for next page link
                next_links = [
                    a for a in soup.find_all("a", href=True)
                    if f"page={page + 1}" in str(a.get("href", ""))
                ]
                if not next_links:
                    break

                page += 1
                logger.info(
                    "Fetching page %d for %s year=%d (%d/%s items so far)",
                    page, self._source_key, self._year, len(all_items), total
                )
        else:
            # Recent decisions mode (last 100)
            url = _FC_RECENT_URL
            content = self._fetch_url_content(url)
            if content is not None:
                self._raw_bytes = content
                self._fetch_http_status = 200
                self._fetch_content_type = "text/html"
                self._fetch_url = url
                html = content.decode("utf-8", errors="replace")
                all_items = self._parse_items(html)
                if self._limit:
                    all_items = all_items[: self._limit]

        return all_items

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        for item in raw:
            url = item.get("url", "")
            url_violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if url_violation:
                continue
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=url or None,
                    payload={
                        "headline": item.get("headline"),
                        "url": url,
                        "neutral_citation": item.get("neutral_citation"),
                        "date": item.get("date"),
                    },
                    source_url=url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key)
        try:
            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = self._raw_bytes
            result.fetch_http_status = self._fetch_http_status
            result.fetch_content_type = self._fetch_content_type
            result.fetch_url = self._fetch_url
            result.parser_version = PARSER_VERSION
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key,
                        headline=p.payload.get("headline"),
                        url=p.source_url,
                        extracted_text=p.payload.get("neutral_citation"),
                        confidence_score=0.9,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
