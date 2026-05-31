"""Canonical field-mapping tests for LawsJusticeXmlAdapter.

Layer: adapter parse() / run() output only — no database.

These tests sit between the parser layer (test_justice_canada_xml_parser.py,
test_justice_laws_xml.py) and the end-to-end DB persistence layer
(test_justice_laws_phase4.py).  They verify that the adapter correctly maps
XML field values to specific canonical payload keys that are not covered at
any other layer.

Gaps covered here:
- payload["jurisdiction"] == "CA-FED"           (hardcoded in adapter)
- external_id == "{unique_id}:{language}"        (format contract)
- payload["short_title"], payload["long_title"]  (statute → payload mapping)
- payload["citation"]                            (official_number → citation)
- sections use "section_label" key, not "label"  (adapter rename)
- sections carry "marginal_note" and "text"
- review_items.headline and .extracted_text      (derived fields)
- result.records_fetched matches index entry count
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.source_adapters.laws_justice_xml import (
    PARSER_VERSION,
    LawsJusticeXmlAdapter,
)
from app.services.source_fetcher import FetchResult

_FIXTURES = Path(__file__).parent / "fixtures" / "sources"


# ---------------------------------------------------------------------------
# Helpers (intentionally local — tests must be self-contained)
# ---------------------------------------------------------------------------

def _fetcher_from_fixtures():
    legis = (_FIXTURES / "legis_sample.xml").read_bytes()
    statute = (_FIXTURES / "c-46_sample.xml").read_bytes()

    def _fetcher(target_url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        content = legis if target_url.endswith("Legis.xml") else statute
        return FetchResult(
            url=target_url,
            final_url=target_url,
            fetched_at=datetime.now(timezone.utc),
            http_status=200,
            content_type="application/xml",
            headers={"content-type": "application/xml"},
            raw_content=content,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=None,
        )

    return _fetcher


def _make_adapter(**kw) -> LawsJusticeXmlAdapter:
    return LawsJusticeXmlAdapter(
        source_key="justice_canada_laws_xml",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
        public_record_authority="official_legislation",
        fetcher=_fetcher_from_fixtures(),
        **kw,
    )


def _eng_instrument(result):
    return next(i for i in result.legal_instruments if i.language == "eng")


def _eng_review_item(result):
    return next(i for i in result.review_items if i.payload.get("language") == "eng")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_canonical_payload_jurisdiction_is_ca_fed() -> None:
    """Adapter hard-codes CA-FED jurisdiction; must survive refactor."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    assert eng.payload["jurisdiction"] == "CA-FED"


def test_canonical_external_id_format() -> None:
    """external_id must be '{unique_id}:{language}' for downstream dedup."""
    adapter = _make_adapter()
    raw = adapter.fetch()
    parsed = adapter.parse(raw)
    eng_record = next(r for r in parsed if r.payload.get("language") == "eng")
    assert eng_record.external_id == "C-46:eng"


def test_canonical_payload_short_title() -> None:
    """short_title comes from statute XML <ShortTitle>."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    assert eng.payload["short_title"] == "Criminal Code"


def test_canonical_payload_long_title() -> None:
    """long_title comes from statute XML <LongTitle>."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    assert eng.payload["long_title"] == "An Act respecting the Criminal Law"


def test_canonical_payload_citation() -> None:
    """citation comes from index XML <OfficialNumber>."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    assert eng.payload["citation"] == "C-46"


def test_canonical_sections_use_section_label_key() -> None:
    """Adapter renames parser 'label' to 'section_label' in payload sections."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    assert len(eng.sections) == 2
    assert eng.sections[0]["section_label"] == "1"
    assert eng.sections[1]["section_label"] == "2"


def test_canonical_sections_include_marginal_note_and_text() -> None:
    """Each section carries marginal_note and text from the statute XML."""
    result = _make_adapter().run()
    eng = _eng_instrument(result)
    sec1 = eng.sections[0]
    assert sec1["marginal_note"] == "Short title"
    assert "Criminal Code" in sec1["text"]


def test_review_item_headline_matches_title() -> None:
    """review_items.headline derives from metadata title, not statute title."""
    result = _make_adapter().run()
    eng_item = _eng_review_item(result)
    assert eng_item.headline == "Criminal Code"


def test_review_item_extracted_text_prefers_long_title() -> None:
    """extracted_text uses long_title when present; short_title as fallback."""
    result = _make_adapter().run()
    eng_item = _eng_review_item(result)
    assert eng_item.extracted_text == "An Act respecting the Criminal Law"


def test_records_fetched_matches_index_entry_count() -> None:
    """records_fetched equals the number of entries in Legis.xml (eng + fra)."""
    result = _make_adapter().run()
    # legis_sample.xml has 2 entries: C-46 eng and C-46 fra
    assert result.records_fetched == 2
