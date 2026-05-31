"""Adapter for Canada's Laws-Justice.gc.ca legislation site.

Handles source key: ``justice_canada_laws_xml``
Parser key: ``laws_justice_html``
Creates: ``ReviewItem`` records only
Authority: ``official_legislation``

Validated against live site (2026-05-06):
- The Criminal Code page (https://laws-lois.justice.gc.ca/eng/acts/C-46/) has
  an "Amendments" <h2> section with a <table> containing amendment citation
  links in the format ``/eng/AnnualStatutes/YYYY_N``
- Each table row has: Amendment Citation link | Amendment date
- The base_url should point to a specific act page (e.g. C-46)

Evidence contract: every run() call that fetches data must set
    result.raw_snapshot_bytes, result.fetch_http_status,
    result.fetch_content_type, and result.fetch_url.
"""

from __future__ import annotations

import logging
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
_BASE_DOMAIN = "https://laws-lois.justice.gc.ca"


class LawsJusticeHtmlAdapter(CanadianSourceAdapter):
    """Fetch recent amendments from laws-lois.justice.gc.ca.

    Monitors the Justice Laws website for newly published or amended statutes
    relevant to criminal justice (Criminal Code, Youth Criminal Justice Act, etc.)
    and creates ``ReviewItem`` records for editorial review.

    Validated structure (2026-05-06):
    - URL: ``https://laws-lois.justice.gc.ca/eng/acts/C-46/``
    - "Amendments" ``<h2>`` section contains a ``<table>``
    - Table rows: ``<td><a href="/eng/AnnualStatutes/YYYY_N">YYYY, c. N</a></td>
      <td>YYYY-MM-DD</td>``
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url
        self._allowed_domains_json = (
            allowed_domains_json or '["laws-lois.justice.gc.ca", "justice.gc.ca"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        # Evidence snapshot fields — populated during fetch().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _parse_amendments(self, html: str) -> list[dict[str, Any]]:
        """Extract amendment citations from the act page.

        Finds the "Amendments" <h2> section and parses the table of
        amendment citation links and dates.
        """
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []

        # Find the Amendments h2 section.
        amend_h2 = soup.find("h2", string=lambda t: t and "Amendments" in t)
        if amend_h2:
            # Find the table in the amendments section.
            table = amend_h2.find_next("table")
            if table:
                for row in table.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    if not cells:
                        continue
                    link_tag = cells[0].find("a", href=True)
                    if not link_tag:
                        continue
                    href = str(link_tag["href"])
                    full_url = (
                        href
                        if href.startswith("http")
                        else _BASE_DOMAIN + href
                    )
                    headline = link_tag.get_text(strip=True)
                    date = cells[1].get_text(strip=True) if len(cells) > 1 else None
                    if headline:
                        items.append(
                            {
                                "url": full_url,
                                "headline": headline,
                                "date": date,
                            }
                        )

        # Fallback: scan all act/statute links if no amendments table found.
        if not items:
            for link in soup.select("a[href]"):
                href = str(link["href"])
                text = link.get_text(strip=True)
                if not text or len(text) < 3:
                    continue
                # Filter for act/statute links
                if "/eng/acts/" in href or "/eng/AnnualStatutes/" in href:
                    full_url = (
                        href
                        if href.startswith("http")
                        else _BASE_DOMAIN + href
                    )
                    items.append({"url": full_url, "headline": text})

        return items

    def fetch(self) -> list[dict[str, Any]]:
        try:
            fetch_result = self._fetcher(self._base_url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "Domain check failed for %s: %s", self._source_key, fetch_result.error
                )
                return []
            # Preserve raw evidence bytes for snapshot contract.
            self._raw_bytes = fetch_result.raw_content
            self._fetch_http_status = fetch_result.http_status
            self._fetch_content_type = fetch_result.content_type or "text/html"
            self._fetch_url = fetch_result.final_url or self._base_url
            raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
            return self._parse_amendments(raw_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", self._source_key, exc)
            return []

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
            # Propagate evidence snapshot fields.
            result.raw_snapshot_bytes = self._raw_bytes
            result.fetch_http_status = self._fetch_http_status
            result.fetch_content_type = self._fetch_content_type
            result.fetch_url = self._fetch_url
            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key,
                        headline=p.payload.get("headline"),
                        url=p.source_url,
                        extracted_text=p.payload.get("date"),
                        confidence_score=0.95,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
