"""Adapter for Justice Canada Laws XML.

Handles source key: ``justice_canada_laws_xml``
Parser key: ``laws_justice_xml``
Creates: ``LegalInstrument`` records and matching ``ReviewItem`` rows only
Authority: ``official_legislation``
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.ingestion.adapters import (
    CanadianSourceAdapter,
    CreatedLegalInstrument,
    CreatedReviewItem,
    IngestionResult,
    ParsedRecord,
)
from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion, parse_allowed_domains
from app.ingestion.parsers.justice_canada.parser import (
    parse_legis_index,
    parse_statute_xml,
)
from app.ingestion.parsers.justice_canada.schema_validator import (
    SchemaValidationError,
    validate_index_xml,
    validate_statute_xml,
)
from app.ingestion.source_rules import check_record_type_allowed

logger = logging.getLogger(__name__)

PARSER_VERSION = "justice_laws_xml_v1"
_RECORD_TYPE = "LegalInstrument"
_DEFAULT_INDEX_URL = "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml"
_DEFAULT_TARGET_UNIQUE_IDS = ("C-46",)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class LawsJusticeXmlAdapter(CanadianSourceAdapter):
    """Fetch and parse Justice Canada legislation XML for legal context."""

    def __init__(
        self,
        source_key: str,
        base_url: str,
        allowed_domains_json: str | None = None,
        public_record_authority: str | None = None,
        fetcher: FetchCallable | None = None,
        target_unique_ids: list[str] | None = None,
    ) -> None:
        self._source_key = source_key
        self._base_url = base_url or _DEFAULT_INDEX_URL
        self._allowed_domains_json = (
            allowed_domains_json
            or '["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]'
        )
        self._allowed_domains = parse_allowed_domains(self._allowed_domains_json)
        self._public_record_authority = public_record_authority
        self._fetcher = fetcher or fetch_for_ingestion
        self._target_unique_ids = set(target_unique_ids or _DEFAULT_TARGET_UNIQUE_IDS)
        self._raw_bytes_parts: list[bytes] = []
        self._fetch_http_status: int | None = None
        self._fetch_content_type: str | None = None
        self._fetch_url: str | None = None

    def _fetch_bytes(self, url: str) -> bytes:
        fetch_result = self._fetcher(url, self._allowed_domains)
        if fetch_result.error:
            raise SchemaValidationError(fetch_result.error)
        content = fetch_result.raw_content or b""
        if not content:
            raise SchemaValidationError(f"Empty XML response from {url}")
        self._raw_bytes_parts.append(
            b"\n<!-- justice-canada-xml-boundary: " + url.encode("utf-8") + b" -->\n"
        )
        self._raw_bytes_parts.append(content)
        self._fetch_http_status = fetch_result.http_status
        self._fetch_content_type = fetch_result.content_type or "application/xml"
        self._fetch_url = fetch_result.final_url or url
        return content

    def fetch(self) -> list[dict[str, Any]]:
        self._raw_bytes_parts = []
        index_xml = self._fetch_bytes(self._base_url)
        validate_index_xml(index_xml)
        index_records = parse_legis_index(index_xml)

        selected = [
            r for r in index_records if r.get("unique_id") in self._target_unique_ids
        ]
        raw_records: list[dict[str, Any]] = []
        for metadata in selected:
            statute_url = metadata.get("link_to_xml")
            if not statute_url:
                raise SchemaValidationError(
                    f"Missing LinkToXML for {metadata.get('unique_id')}"
                )
            statute_xml = self._fetch_bytes(str(statute_url))
            validate_statute_xml(statute_xml, str(metadata.get("unique_id")))
            statute = parse_statute_xml(statute_xml)
            if statute is None:
                raise SchemaValidationError(
                    f"Could not parse statute {metadata.get('unique_id')}"
                )
            raw_records.append(
                {
                    "metadata": metadata,
                    "statute": statute,
                    "source_url": statute_url,
                }
            )

        return raw_records

    def parse(self, raw: list[dict[str, Any]]) -> list[ParsedRecord]:
        records: list[ParsedRecord] = []
        for item in raw:
            metadata = item["metadata"]
            statute = item["statute"]
            source_url = item.get("source_url") or metadata.get("link_to_xml")

            violation = check_record_type_allowed(
                "ReviewItem",
                self._public_record_authority,
                '["ReviewItem"]',
            )
            if violation:
                continue

            sections = [
                {
                    "section_label": section.get("label"),
                    "subsection_label": section.get("subsection_label"),
                    "marginal_note": section.get("marginal_note"),
                    "text": section.get("text"),
                    "path": section.get("path"),
                    "source_xml_node_id": section.get("source_xml_node_id"),
                }
                for section in statute.get("sections", [])
                if section.get("label") and section.get("text")
            ]
            payload = {
                "record_type": _RECORD_TYPE,
                "source_key": self._source_key,
                "source_quality": "official_legislation",
                "privacy_status": "public_record_private_until_review",
                "publish_recommendation": "review_required",
                "jurisdiction": "CA-FED",
                "instrument_type": metadata.get("instrument_type") or metadata.get("law_type"),
                "unique_id": metadata.get("unique_id"),
                "language": metadata.get("language"),
                "title": metadata.get("title"),
                "short_title": statute.get("short_title"),
                "long_title": statute.get("long_title"),
                "citation": metadata.get("official_number"),
                "chapter_or_instrument_number": metadata.get("official_number"),
                "current_to_date": metadata.get("current_to_date"),
                "consolidated_number": statute.get("consolidated_number"),
                "link_to_xml": metadata.get("link_to_xml"),
                "link_to_html_toc": metadata.get("link_to_html_toc"),
                "parser_version": PARSER_VERSION,
                "sections": sections,
            }
            records.append(
                ParsedRecord(
                    source_name=self._source_key,
                    source_key=self._source_key,
                    record_type=_RECORD_TYPE,
                    external_id=f"{metadata.get('unique_id')}:{metadata.get('language')}",
                    payload=payload,
                    source_url=source_url,
                )
            )
        return records

    def run(self) -> IngestionResult:
        result = IngestionResult(source_key=self._source_key, parser_version=PARSER_VERSION)
        try:
            raw = self.fetch()
            result.records_fetched = len(raw)
            result.raw_snapshot_bytes = b"".join(self._raw_bytes_parts)
            result.fetch_http_status = self._fetch_http_status
            result.fetch_content_type = self._fetch_content_type or "application/xml"
            result.fetch_url = self._fetch_url or self._base_url

            parsed = self.parse(raw)
            result.records_skipped = len(raw) - len(parsed)
            for p in parsed:
                sections = p.payload.get("sections") or []
                result.legal_instruments.append(
                    CreatedLegalInstrument(
                        source_key=p.source_key or self._source_key,
                        instrument_type=p.payload["instrument_type"],
                        unique_id=p.payload["unique_id"],
                        language=p.payload["language"],
                        title=p.payload["title"],
                        payload=p.payload,
                        sections=sections,
                        source_url=p.source_url,
                    )
                )
                result.review_items.append(
                    CreatedReviewItem(
                        source_key=p.source_key or self._source_key,
                        headline=p.payload.get("title"),
                        url=p.source_url,
                        extracted_text=p.payload.get("long_title")
                        or p.payload.get("short_title"),
                        confidence_score=0.98,
                        payload=p.payload,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in %s XML adapter", self._source_key)
            result.errors.append(str(exc))
            result.records_fetched = 0
            result.records_skipped = 0
            result.review_items.clear()
            result.legal_instruments.clear()
            result.raw_snapshot_bytes = None
        return result
