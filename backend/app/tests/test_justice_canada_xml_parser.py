"""Tests for the Justice Canada XML parser (structural / deterministic)."""

from __future__ import annotations

import pytest

from app.ingestion.parsers.justice_canada.parser import (
    parse_legis_index,
    parse_statute_xml,
)

# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------

_LEGIS_INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
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
    <Act>
      <UniqueId>A-1</UniqueId>
      <Language>eng</Language>
      <Title>Access to Information Act</Title>
      <OfficialNumber>R.S.C., 1985, c. A-1</OfficialNumber>
      <CurrentToDate>2024-01-01</CurrentToDate>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/XML/A-1.xml</LinkToXML>
    </Act>
  </Acts>
  <Regulations>
    <Regulation>
      <UniqueId>REG-001</UniqueId>
      <Language>eng</Language>
      <Title>Some Regulation</Title>
      <OfficialNumber>SOR/2020-1</OfficialNumber>
      <CurrentToDate>2024-06-01</CurrentToDate>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/regulations/SOR-2020-1/XML/SOR-2020-1.xml</LinkToXML>
    </Regulation>
  </Regulations>
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
    <Chapter>
      <ConsolidatedNumber>C-46</ConsolidatedNumber>
    </Chapter>
  </Identification>
  <Body>
    <Section xmlns:lims="http://justice.gc.ca/lims" lims:id="sec-1">
      <Label>1</Label>
      <MarginalNote>Short title</MarginalNote>
      <Text>This Act may be cited as the Criminal Code.</Text>
    </Section>
    <Section xmlns:lims="http://justice.gc.ca/lims" lims:id="sec-2">
      <Label>2</Label>
      <MarginalNote>Definitions</MarginalNote>
      <Subsection>
        <Label>(1)</Label>
        <Text>In this Act, "act" means an act or omission.</Text>
      </Subsection>
      <Subsection>
        <Label>(2)</Label>
        <Text>Words importing the masculine include the feminine.</Text>
      </Subsection>
    </Section>
    <Section xmlns:lims="http://justice.gc.ca/lims" lims:id="sec-empty">
      <Label>3</Label>
    </Section>
  </Body>
</Statute>"""


# ---------------------------------------------------------------------------
# parse_legis_index tests
# ---------------------------------------------------------------------------

class TestParseLegisIndex:
    def test_returns_list(self):
        records = parse_legis_index(_LEGIS_INDEX_XML)
        assert isinstance(records, list)

    def test_parses_acts_and_regulations(self):
        records = parse_legis_index(_LEGIS_INDEX_XML)
        # 2 Acts + 1 Regulation
        assert len(records) == 3

    def test_act_fields(self):
        records = parse_legis_index(_LEGIS_INDEX_XML)
        c46 = next(r for r in records if r["unique_id"] == "C-46")
        assert c46["title"] == "Criminal Code"
        assert c46["language"] == "eng"
        assert c46["instrument_type"] == "Act"
        assert "laws-lois.justice.gc.ca" in c46["link_to_xml"]
        assert c46["current_to_date"] == "2024-01-01"
        assert c46["official_number"] == "R.S.C., 1985, c. C-46"

    def test_regulation_instrument_type(self):
        records = parse_legis_index(_LEGIS_INDEX_XML)
        reg = next(r for r in records if r["unique_id"] == "REG-001")
        assert reg["instrument_type"] == "Regulation"

    def test_missing_required_fields_skipped(self):
        partial_xml = b"""<ActsRegsList>
          <Acts>
            <Act>
              <UniqueId>NOLINK</UniqueId>
              <Language>eng</Language>
              <Title>No Link Act</Title>
            </Act>
          </Acts>
        </ActsRegsList>"""
        records = parse_legis_index(partial_xml)
        # Missing LinkToXML → skipped
        assert len(records) == 0

    def test_wrong_root_tag_raises(self):
        with pytest.raises(ValueError, match="ActsRegsList"):
            parse_legis_index(b"<NotTheRightRoot/>")

    def test_empty_collections_returns_empty(self):
        xml = b"<ActsRegsList><Acts/><Regulations/></ActsRegsList>"
        assert parse_legis_index(xml) == []


# ---------------------------------------------------------------------------
# parse_statute_xml tests
# ---------------------------------------------------------------------------

class TestParseStatuteXml:
    def test_returns_dict(self):
        result = parse_statute_xml(_STATUTE_XML)
        assert isinstance(result, dict)

    def test_basic_identification(self):
        result = parse_statute_xml(_STATUTE_XML)
        assert result["short_title"] == "Criminal Code"
        assert result["long_title"] == "An Act respecting the criminal law"
        assert result["citation"] == "R.S.C., 1985, c. C-46"
        assert result["statute_id"] == "C-46"

    def test_dates(self):
        result = parse_statute_xml(_STATUTE_XML)
        assert result["current_date"] == "2024-01-01"
        assert result["last_amended_date"] == "2023-12-01"
        assert result["in_force_start_date"] == "1985-01-01"

    def test_consolidated_number(self):
        result = parse_statute_xml(_STATUTE_XML)
        assert result["consolidated_number"] == "C-46"

    def test_sections_extracted(self):
        result = parse_statute_xml(_STATUTE_XML)
        sections = result["sections"]
        assert len(sections) >= 1

    def test_section_fields_present(self):
        result = parse_statute_xml(_STATUTE_XML)
        sec1 = next(s for s in result["sections"] if s["label"] == "1")
        assert sec1["text"] == "This Act may be cited as the Criminal Code."
        assert sec1["marginal_note"] == "Short title"
        assert sec1["path"].startswith("section:")
        assert sec1["section_key"].startswith("justice-sec-")

    def test_subsections_extracted(self):
        result = parse_statute_xml(_STATUTE_XML)
        subsecs = [s for s in result["sections"] if s["subsection_label"] is not None]
        assert len(subsecs) == 2
        sub1 = next(s for s in subsecs if s["subsection_label"] == "(1)")
        assert "act or omission" in sub1["text"]

    def test_empty_section_skipped(self):
        # Section 3 has no Text or Subsection with text → should not appear
        result = parse_statute_xml(_STATUTE_XML)
        labels = [s["label"] for s in result["sections"]]
        assert "3" not in labels

    def test_section_key_is_stable(self):
        # Parsing the same XML twice yields the same section keys (deterministic)
        r1 = parse_statute_xml(_STATUTE_XML)
        r2 = parse_statute_xml(_STATUTE_XML)
        keys1 = {s["section_key"] for s in r1["sections"]}
        keys2 = {s["section_key"] for s in r2["sections"]}
        assert keys1 == keys2

    def test_section_key_uniqueness(self):
        result = parse_statute_xml(_STATUTE_XML)
        keys = [s["section_key"] for s in result["sections"]]
        assert len(keys) == len(set(keys))

    def test_wrong_root_raises(self):
        with pytest.raises(ValueError, match="Statute"):
            parse_statute_xml(b"<NotStatute/>")

    def test_missing_identification_raises(self):
        xml = b"""<Statute xmlns:lims="http://justice.gc.ca/lims" lims:id="X">
          <Body><Section><Label>1</Label><Text>Text.</Text></Section></Body>
        </Statute>"""
        with pytest.raises(ValueError, match="Identification"):
            parse_statute_xml(xml)

    def test_missing_body_raises(self):
        xml = b"""<Statute xmlns:lims="http://justice.gc.ca/lims" lims:id="X">
          <Identification>
            <ShortTitle>Test</ShortTitle>
            <LongTitle>Test Act</LongTitle>
          </Identification>
        </Statute>"""
        with pytest.raises(ValueError, match="Body"):
            parse_statute_xml(xml)
