"""Adapter for Saskatchewan Legislative Assembly Hansard index.

Handles source key: ``sk_legislature_hansard``
Parser key: ``sk_legislature_html``
Creates: ``ReviewItem`` records only
Authority: ``official_legislation``

Validated against live site (2026-05-06):
- URL: https://www.legassembly.sk.ca/legislative-business/debates-hansard/
- Page has a "Hansard Indexes" section with a table
- Table columns: Legislature | Session | Timeframe | SubjectIndex | SpeakerIndex
- Subject index links: https://docs.legassembly.sk.ca/legdocs/Assembly/Debates/Indexes/NN/NNL-SU-full.html
- Speaker index links: https://docs.legassembly.sk.ca/legdocs/Assembly/Debates/Indexes/NN/NNL-SP-full.html
- Current legislature: 30th (2024-)

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
_HANSARD_BASE = "https://www.legassembly.sk.ca"
_DOCS_BASE = "https://docs.legassembly.sk.ca"


class SKLegislatureHtmlAdapter(CanadianSourceAdapter):
    """Fetch Saskatchewan Legislative Assembly Hansard index for ReviewItem candidates.

    The Legislative Assembly publishes Hansard (debate) indexes on its website.
    This adapter fetches the Hansard index page, extracts legislature/session
    index links, and creates ReviewItem records for editorial review.

    All records require manual review before publication.

    Validated structure (2026-05-06):
    - URL: ``https://www.legassembly.sk.ca/legislative-business/debates-hansard/``
    - Table with columns: Legislature, Session, Timeframe, SubjectIndex, SpeakerIndex
    - Index links point to ``docs.legassembly.sk.ca``
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
        self._base_url = base_url or (
            _HANSARD_BASE + "/legislative-business/debates-hansard/"
        )
        self._allowed_domains_json = (
            allowed_domains_json
            or '["legassembly.sk.ca", "www.legassembly.sk.ca", "docs.legassembly.sk.ca"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        # Evidence snapshot fields — populated during fetch().
        self._raw_bytes: bytes | None = None
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _parse_hansard_index(self, html: str) -> list[dict[str, Any]]:
        """Extract Hansard index links from the Legislative Assembly Hansard page.

        Finds the table with Legislature/Session/Timeframe/SubjectIndex/SpeakerIndex
        columns and extracts the index links for each legislature.
        """
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []

        # Find the Hansard Indexes table.
        # The table has headers: Legislature, Session, Timeframe, SubjectIndex, SpeakerIndex
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            if "Legislature" not in headers and "SubjectIndex" not in headers:
                continue

            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                # Skip header row
                if cells[0].name == "th":
                    continue

                legislature = cells[0].get_text(strip=True)
                session = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                timeframe = cells[2].get_text(strip=True) if len(cells) > 2 else ""

                # Extract subject index link (column 3)
                subject_link = cells[3].find("a", href=True) if len(cells) > 3 else None
                if subject_link:
                    href = str(subject_link["href"])
                    full_url = (
                        href if href.startswith("http") else _HANSARD_BASE + href
                    )
                    headline = (
                        f"Saskatchewan Hansard – {legislature} Legislature"
                        f"{', Session ' + session if session else ''}"
                        f"{', ' + timeframe if timeframe else ''}"
                        " – Subject Index"
                    )
                    items.append(
                        {
                            "url": full_url,
                            "headline": headline,
                            "legislature": legislature,
                            "session": session,
                            "timeframe": timeframe,
                            "index_type": "subject",
                        }
                    )

                # Extract speaker index link (column 4)
                speaker_link = cells[4].find("a", href=True) if len(cells) > 4 else None
                if speaker_link:
                    href = str(speaker_link["href"])
                    full_url = (
                        href if href.startswith("http") else _HANSARD_BASE + href
                    )
                    headline = (
                        f"Saskatchewan Hansard – {legislature} Legislature"
                        f"{', Session ' + session if session else ''}"
                        f"{', ' + timeframe if timeframe else ''}"
                        " – Speaker Index"
                    )
                    items.append(
                        {
                            "url": full_url,
                            "headline": headline,
                            "legislature": legislature,
                            "session": session,
                            "timeframe": timeframe,
                            "index_type": "speaker",
                        }
                    )

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
            return self._parse_hansard_index(raw_text)
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
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=url or None,
                    payload={
                        "headline": item.get("headline"),
                        "url": url,
                        "legislature": item.get("legislature"),
                        "session": item.get("session"),
                        "timeframe": item.get("timeframe"),
                        "index_type": item.get("index_type"),
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
                        extracted_text=p.payload.get("timeframe"),
                        confidence_score=0.9,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s adapter", self._source_key)
            result.errors.append(str(exc))
        return result
