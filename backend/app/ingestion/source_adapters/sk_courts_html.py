"""Adapter for Saskatchewan Courts HTML decision pages.

Handles source keys: ``sk_courts_qb_decisions``, ``sk_courts_ca_decisions``
Parser key: ``sk_courts_html``
Creates: ``ReviewItem`` records only (court decisions require human review before publish)
Authority: ``official_court_record``

Validated against live site (2026-05-06):
- https://sasklawcourts.ca/saskatchewan-court-decisions/ explains that
  decisions are published on CanLII (https://www.canlii.org/en/sk/)
- The courts website itself does not host decision documents
- CanLII blocks automated scraping (HTTP 403)
- The courts page links to:
    - https://www.canlii.org/en/sk/skkb/ (King's Bench)
    - https://www.canlii.org/en/sk/skca/ (Court of Appeal)
    - https://www.canlii.org/en/sk/skpc/ (Provincial Court)

Design decision: This adapter fetches the Saskatchewan Courts decisions
landing page and extracts CanLII database links as ReviewItem references.
These are reference links, not full decision documents. The source requires
manual review before any decisions are treated as evidence.

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

# The Saskatchewan Courts decisions landing page
_SK_DECISIONS_URL = "https://sasklawcourts.ca/saskatchewan-court-decisions/"

# CanLII court database URLs for Saskatchewan courts
_CANLII_COURTS = {
    "skkb": ("https://www.canlii.org/en/sk/skkb/", "Saskatchewan Court of King's Bench"),
    "skca": ("https://www.canlii.org/en/sk/skca/", "Saskatchewan Court of Appeal"),
    "skpc": ("https://www.canlii.org/en/sk/skpc/", "Saskatchewan Provincial Court"),
}


class SKCourtsHtmlAdapter(CanadianSourceAdapter):
    """Fetch Saskatchewan Courts decisions landing page for ReviewItem references.

    The Saskatchewan Courts website directs users to CanLII for published
    decisions. This adapter fetches the courts decisions landing page,
    extracts CanLII database links, and creates ReviewItem records pointing
    to the CanLII databases for each court.

    All records require manual review before publication.

    Validated structure (2026-05-06):
    - URL: ``https://sasklawcourts.ca/saskatchewan-court-decisions/``
    - Contains links to CanLII databases for each court
    - CanLII itself blocks automated scraping (HTTP 403)
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
        self._base_url = base_url or _SK_DECISIONS_URL
        self._allowed_domains_json = (
            allowed_domains_json
            or '["sasklawcourts.ca", "www.sasklawcourts.ca", "canlii.org", "www.canlii.org"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        # Evidence snapshot fields — populated during fetch().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _parse_index_page(self, html: str) -> list[dict[str, Any]]:
        """Extract CanLII database links from the Saskatchewan Courts decisions page.

        Looks for links to canlii.org databases for Saskatchewan courts.
        """
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []

        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            text = link.get_text(strip=True)
            # Only CanLII links with meaningful text
            if "canlii.org" in href and text and len(text) > 3:
                items.append(
                    {
                        "url": href,
                        "headline": text,
                    }
                )

        # If no CanLII links found on the page, use the known court databases.
        if not items:
            logger.info(
                "No CanLII links found on %s; using known court database URLs",
                self._source_key,
            )
            for court_id, (url, name) in _CANLII_COURTS.items():
                items.append({"url": url, "headline": name})

        return items

    def fetch(self) -> list[dict[str, Any]]:
        fetch_url = self._base_url or _SK_DECISIONS_URL
        try:
            fetch_result = self._fetcher(fetch_url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "Domain check failed for %s: %s", self._source_key, fetch_result.error
                )
                return []
            # Preserve raw evidence bytes for snapshot contract.
            self._raw_bytes = fetch_result.raw_content
            self._fetch_http_status = fetch_result.http_status
            self._fetch_content_type = fetch_result.content_type or "text/html"
            self._fetch_url = fetch_result.final_url or fetch_url
            raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
            return self._parse_index_page(raw_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch %s: %s", self._source_key, exc)
            return []

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        for item in raw:
            url = item.get("url", "")
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                continue
            # Allow both sasklawcourts.ca and canlii.org URLs.
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
                        extracted_text=None,
                        confidence_score=0.0,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
