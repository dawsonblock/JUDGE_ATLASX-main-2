"""Tests for LawsJusticeXmlAdapter (mocked network — no HTTP calls)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.ingestion.source_adapters.laws_justice_xml import (
    LawsJusticeXmlAdapter,
)

# ---------------------------------------------------------------------------
# Minimal XML payloads (same as parser tests, self-contained here)
# ---------------------------------------------------------------------------

_INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ActsRegsList>
  <Acts>
    <Act>
      <UniqueId>C-46</UniqueId>
      <Language>eng</Language>
      <Title>Criminal Code</Title>
      <OfficialNumber>R.S.C., 1985, c. C-46</OfficialNumber>
      <CurrentToDate>2024-01-01</CurrentToDate>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/XML/C-46.xml</LinkToXML>
      <LinkToHTMLToC>https://laws-lois.justice.gc.ca/eng/acts/C-46/</LinkToHTMLToC>
    </Act>
  </Acts>
  <Regulations/>
</ActsRegsList>"""

_STATUTE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Statute xmlns:lims="http://justice.gc.ca/lims"
         lims:id="C-46"
         lims:current-date="2024-01-01"
         lims:lastAmendedDate="2023-12-01"
         lims:inforce-start-date="1985-01-01">
  <Identification>
    <ShortTitle>Criminal Code</ShortTitle>
    <LongTitle>An Act respecting the criminal law</LongTitle>
    <Citation>R.S.C., 1985, c. C-46</Citation>
    <Chapter><ConsolidatedNumber>C-46</ConsolidatedNumber></Chapter>
  </Identification>
  <Body>
    <Section xmlns:lims="http://justice.gc.ca/lims" lims:id="sec-1">
      <Label>1</Label>
      <MarginalNote>Short title</MarginalNote>
      <Text>This Act may be cited as the Criminal Code.</Text>
    </Section>
  </Body>
</Statute>"""


# ---------------------------------------------------------------------------
# Fetch stub
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    raw_content: bytes | None = None
    error: str | None = None
    http_status: int | None = 200
    content_type: str | None = "application/xml"
    final_url: str | None = None


def _make_fetcher(responses: dict[str, bytes]):
    """Returns a fetcher that serves fixed XML per URL."""

    def fetcher(url: str, _allowed_domains):
        content = responses.get(url)
        if content is None:
            return FetchResult(error=f"No fixture for {url}")
        return FetchResult(raw_content=content, final_url=url)

    return fetcher


_DEFAULT_BASE_URL = "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml"
_C46_URL = "https://laws-lois.justice.gc.ca/eng/XML/C-46.xml"

_DEFAULT_FETCHER = _make_fetcher({
    _DEFAULT_BASE_URL: _INDEX_XML,
    _C46_URL: _STATUTE_XML,
})


def _make_adapter(**kwargs) -> LawsJusticeXmlAdapter:
    defaults = dict(
        source_key="justice_canada_laws_xml",
        base_url=_DEFAULT_BASE_URL,
        public_record_authority="official_legislation",
        fetcher=_DEFAULT_FETCHER,
        target_unique_ids=["C-46"],
    )
    defaults.update(kwargs)
    return LawsJusticeXmlAdapter(**defaults)


# ---------------------------------------------------------------------------
# fetch() tests
# ---------------------------------------------------------------------------

class TestLawsJusticeXmlAdapterFetch:
    def test_fetch_returns_list(self):
        adapter = _make_adapter()
        raw = adapter.fetch()
        assert isinstance(raw, list)

    def test_fetch_returns_one_item_for_c46(self):
        adapter = _make_adapter()
        raw = adapter.fetch()
        assert len(raw) == 1

    def test_fetch_item_has_metadata_and_statute(self):
        adapter = _make_adapter()
        raw = adapter.fetch()
        item = raw[0]
        assert "metadata" in item
        assert "statute" in item
        assert "source_url" in item

    def test_fetch_metadata_unique_id(self):
        adapter = _make_adapter()
        raw = adapter.fetch()
        assert raw[0]["metadata"]["unique_id"] == "C-46"

    def test_fetch_statute_short_title(self):
        adapter = _make_adapter()
        raw = adapter.fetch()
        assert raw[0]["statute"]["short_title"] == "Criminal Code"

    def test_fetch_skips_unmatched_unique_ids(self):
        adapter = _make_adapter(target_unique_ids=["NONEXISTENT"])
        raw = adapter.fetch()
        assert raw == []

    def test_fetch_error_on_empty_response(self):
        from app.ingestion.parsers.justice_canada.schema_validator import (
            SchemaValidationError,
        )

        empty_fetcher = _make_fetcher({_DEFAULT_BASE_URL: b""})
        adapter = _make_adapter(fetcher=empty_fetcher)
        with pytest.raises(SchemaValidationError):
            adapter.fetch()

    def test_fetch_error_on_fetcher_failure(self):
        from app.ingestion.parsers.justice_canada.schema_validator import (
            SchemaValidationError,
        )

        def bad_fetcher(url, domains):
            return FetchResult(error="Connection refused")

        adapter = _make_adapter(fetcher=bad_fetcher)
        with pytest.raises(SchemaValidationError, match="Connection refused"):
            adapter.fetch()


# ---------------------------------------------------------------------------
# parse() tests
# ---------------------------------------------------------------------------

class TestLawsJusticeXmlAdapterParse:
    def _fetch_and_parse(self, **kwargs):
        adapter = _make_adapter(**kwargs)
        raw = adapter.fetch()
        return adapter.parse(raw)

    def test_parse_returns_list(self):
        records = self._fetch_and_parse()
        assert isinstance(records, list)

    def test_parse_returns_one_record(self):
        records = self._fetch_and_parse()
        assert len(records) == 1

    def test_parsed_record_type(self):
        records = self._fetch_and_parse()
        assert records[0].record_type == "LegalInstrument"

    def test_parsed_source_key(self):
        records = self._fetch_and_parse()
        assert records[0].source_key == "justice_canada_laws_xml"

    def test_parsed_external_id_format(self):
        records = self._fetch_and_parse()
        # Should be "<UniqueId>:<Language>"
        assert records[0].external_id == "C-46:eng"

    def test_parsed_payload_fields(self):
        records = self._fetch_and_parse()
        payload = records[0].payload
        assert payload["record_type"] == "LegalInstrument"
        assert payload["source_quality"] == "official_legislation"
        assert payload["jurisdiction"] == "CA-FED"
        assert payload["unique_id"] == "C-46"
        assert payload["short_title"] == "Criminal Code"
        assert payload["publish_recommendation"] == "review_required"

    def test_parsed_payload_has_sections(self):
        records = self._fetch_and_parse()
        sections = records[0].payload["sections"]
        assert isinstance(sections, list)
        assert len(sections) >= 1

    def test_parsed_payload_privacy_status(self):
        records = self._fetch_and_parse()
        assert (
            records[0].payload["privacy_status"]
            == "public_record_private_until_review"
        )

    def test_parsed_source_url(self):
        records = self._fetch_and_parse()
        assert records[0].source_url == _C46_URL

    def test_parse_empty_raw_returns_empty(self):
        adapter = _make_adapter()
        assert adapter.parse([]) == []


# ---------------------------------------------------------------------------
# run() smoke test
# ---------------------------------------------------------------------------

class TestLawsJusticeXmlAdapterRun:
    def test_run_returns_ingestion_result(self):
        from app.ingestion.adapters import IngestionResult

        adapter = _make_adapter()
        result = adapter.run()
        assert isinstance(result, IngestionResult)

    def test_run_source_key_in_result(self):
        adapter = _make_adapter()
        result = adapter.run()
        assert result.source_key == "justice_canada_laws_xml"

    def test_run_on_fetch_error_returns_error_result(self):
        def bad_fetcher(url, domains):
            return FetchResult(error="timeout")

        adapter = _make_adapter(fetcher=bad_fetcher)
        result = adapter.run()
        assert result.errors
        assert result.success is False
