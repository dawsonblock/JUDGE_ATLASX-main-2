"""Adapter for Supreme Court of Canada decisions via the Lexum/SCC RSS feed.

Handles source key: ``scc_decisions``
Parser key: ``scc_lexum_api``
Creates: ``ReviewItem`` records only
Authority: ``official_court_record``

Validated against live site (2026-05-06):
- RSS feed: https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do
- Returns 100 items (recent + updated decisions)
- Item structure: <title>, <link>, <description>, <date> (NOT <pubDate>)
- Title format: "  CaseName\\n  - NeutralCitation\\n  - YYYY-MM-DD\\n"
  (needs strip + normalization)
- Link: https://decisions.scc-csc.ca/scc-csc/scc-csc/en/item/NNNNN/index.do

Evidence contract: every run() call that fetches data must set
    result.raw_snapshot_bytes, result.fetch_http_status,
    result.fetch_content_type, and result.fetch_url.
"""

from __future__ import annotations

import logging
import re
from typing import Any

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

# Public SCC decision RSS/Atom feed (no API key needed for recent decisions)
_SCC_RSS_URL = "https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do"

# Regex to extract neutral citation from title
# e.g. "Quebec (Attorney General) v. Lalande\n- 2026 SCC 13\n- 2026-05-01"
_CITATION_PATTERN = re.compile(r"-\s*(\d{4}\s+SCC\s+\d+)", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"-\s*(\d{4}-\d{2}-\d{2})\s*$")


def _clean_title(raw_title: str) -> tuple[str, str | None, str | None]:
    """Parse SCC RSS title into (case_name, neutral_citation, date).

    Live title format (whitespace-heavy):
        "  Quebec (Attorney General) v. Lalande\\n            - 2026 SCC 13\\n    - 2026-05-01\\n"
    """
    # Collapse whitespace and split on " - "
    text = " ".join(raw_title.split())
    # Extract neutral citation
    citation_match = _CITATION_PATTERN.search(text)
    neutral_citation = citation_match.group(1).strip() if citation_match else None
    # Extract date
    date_match = _DATE_PATTERN.search(text)
    date = date_match.group(1) if date_match else None
    # Case name is everything before the first " - YYYY"
    case_name = re.split(r"\s+-\s+\d{4}", text)[0].strip()
    return case_name, neutral_citation, date


class SCCLexumApiAdapter(CanadianSourceAdapter):
    """Fetch Supreme Court of Canada decisions and produce ReviewItem candidates.

    The SCC publishes decisions through decisions.scc-csc.ca.  This adapter
    uses the site's RSS feed for recent decisions.

    All records require manual review before publication.

    Validated structure (2026-05-06):
    - RSS URL: ``https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do``
    - 100 items per feed (recent + updated)
    - Fields: ``<title>``, ``<link>``, ``<description>``, ``<date>``
    - Title needs whitespace normalization
    """

    def __init__(
        self,
        source_key: str,
        base_url: str,
        api_key: str | None = None,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        fetcher: FetchCallable | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url
        self._api_key = api_key
        self._allowed_domains_json = (
            allowed_domains_json
            or '["decisions.scc-csc.ca", "scc-csc.ca", "lexum.com"]'
        )
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        # Evidence snapshot fields — populated during _fetch_rss().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _fetch_rss(self) -> list[dict[str, Any]]:
        """Fetch and parse the SCC RSS feed for recent decisions."""
        import xml.etree.ElementTree as ET  # stdlib — safe

        url = _SCC_RSS_URL
        try:
            fetch_result = self._fetcher(url, self._allowed_domains)
            if fetch_result.error:
                logger.warning(
                    "RSS URL blocked for %s: %s", self._source_key, fetch_result.error
                )
                return []
            # Preserve raw evidence bytes for snapshot contract.
            self._raw_bytes = fetch_result.raw_content
            self._fetch_http_status = fetch_result.http_status
            self._fetch_content_type = fetch_result.content_type or "application/rss+xml"
            self._fetch_url = fetch_result.final_url or url
            raw_text = (fetch_result.raw_content or b"").decode("utf-8", errors="replace")
            root = ET.fromstring(raw_text)
            items: list[dict[str, Any]] = []
            for item in root.iter("item"):
                entry: dict[str, Any] = {}
                for child in item:
                    tag = child.tag.split("}")[-1]  # strip namespace
                    entry[tag] = child.text
                items.append(entry)
            return items
        except Exception as exc:  # noqa: BLE001
            logger.error("SCC RSS fetch failed for %s: %s", self._source_key, exc)
            return []

    def fetch(self) -> list[dict[str, Any]]:
        if self._api_key:
            # Lexum API key is present. The public RSS feed provides the last
            # 100 decisions; for historical bulk access, the Lexum search API
            # at https://lexum.com/ requires a commercial API key.
            # When a key is configured (JTA_LEXUM_API_KEY), it is passed here
            # for future bulk implementation. For now, RSS is used for all fetches.
            logger.info(
                "Lexum API key configured for %s; using RSS feed for recent decisions. "
                "Historical bulk access via Lexum API is available when implemented.",
                self._source_key,
            )
        return self._fetch_rss()

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        for item in raw:
            violation = check_record_type_allowed(
                _RECORD_TYPE,
                self._public_record_authority,
                f'["{_RECORD_TYPE}"]',
            )
            if violation:
                continue
            url = item.get("link") or ""
            raw_title = item.get("title") or ""
            # Normalize the whitespace-heavy title.
            case_name, neutral_citation, date = _clean_title(raw_title)
            # Use the <date> field (live feed uses <date>, not <pubDate>).
            pub_date = item.get("date") or item.get("pubDate")
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=url or None,
                    payload={
                        "headline": case_name or raw_title.strip(),
                        "url": url,
                        "neutral_citation": neutral_citation,
                        "published_at": date or pub_date,
                        "description": item.get("description"),
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
                        extracted_text=p.payload.get("neutral_citation"),
                        confidence_score=0.95,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
