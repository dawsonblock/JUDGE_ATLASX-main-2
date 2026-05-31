"""Unit tests for Justice Canada law parser and schema validator."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.ingestion.parsers.justice_canada.parser import (
    parse_legis_index,
    parse_statute_xml,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "sources"
from app.ingestion.parsers.justice_canada.schema_validator import (
    SchemaValidationError,
    validate_index_xml,
    validate_statute_xml,
)


class TestSchemaValidatorIndex:
    """Tests for Legis.xml (master index) schema validation."""
    
    def test_validate_index_xml_valid(self):
        """Valid Legis.xml passes validation."""
        valid_xml = b"""<?xml version="1.0"?>
<ActsRegsList>
  <Acts>
    <Act>
      <UniqueId>C-46</UniqueId>
      <Language>eng</Language>
      <Title>Criminal Code</Title>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/XML/C-46.xml</LinkToXML>
      <LinkToHTMLToC>https://laws-lois.justice.gc.ca/eng/acts/C-46/index.html</LinkToHTMLToC>
      <OfficialNumber>C-46</OfficialNumber>
      <CurrentToDate>2026-03-17</CurrentToDate>
    </Act>
  </Acts>
</ActsRegsList>
"""
        assert validate_index_xml(valid_xml) is True

    def test_validate_index_xml_invalid_root(self):
        with pytest.raises(SchemaValidationError):
            validate_index_xml(b"<NotActsRegsList />")


class TestParserLegisIndex:
    """Tests for parse_legis_index()."""
    
    def test_parse_legis_index_criminal_code(self):
        """Parse Legis.xml with Criminal Code."""
        xml = b"""<?xml version="1.0"?>
<ActsRegsList>
  <Acts>
    <Act>
      <UniqueId>C-46</UniqueId>
      <OfficialNumber>C-46</OfficialNumber>
      <Language>eng</Language>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/XML/C-46.xml</LinkToXML>
      <LinkToHTMLToC>https://laws-lois.justice.gc.ca/eng/acts/C-46/index.html</LinkToHTMLToC>
      <Title>Criminal Code</Title>
      <CurrentToDate>2026-03-17</CurrentToDate>
    </Act>
  </Acts>
</ActsRegsList>
"""
        records = parse_legis_index(xml)
        
        assert len(records) == 1
        assert records[0]["unique_id"] == "C-46"
        assert records[0]["language"] == "eng"
        assert records[0]["title"] == "Criminal Code"
        assert records[0]["law_type"] == "Act"
        assert "C-46.xml" in records[0]["link_to_xml"]

    def test_parse_legis_index_includes_regulations(self):
        xml = b"""<?xml version=\"1.0\"?>
<ActsRegsList>
  <Regulations>
    <Regulation>
      <UniqueId>SOR-2002-227</UniqueId>
      <OfficialNumber>SOR/2002-227</OfficialNumber>
      <Language>eng</Language>
      <LinkToXML>https://laws-lois.justice.gc.ca/eng/XML/SOR-2002-227.xml</LinkToXML>
      <LinkToHTMLToC>https://laws-lois.justice.gc.ca/eng/regulations/SOR-2002-227/index.html</LinkToHTMLToC>
      <Title>Food and Drug Regulations</Title>
      <CurrentToDate>2026-01-10</CurrentToDate>
    </Regulation>
  </Regulations>
</ActsRegsList>
"""
        records = parse_legis_index(xml)
        assert len(records) == 1
        assert records[0]["instrument_type"] == "Regulation"
        assert records[0]["unique_id"] == "SOR-2002-227"


class TestParserStatuteXml:
    """Tests for parse_statute_xml()."""
    
    def test_parse_statute_xml_criminal_code(self):
        """Parse Criminal Code statute XML."""
        xml = b"""<?xml version="1.0"?>
<Statute xmlns:lims="http://justice.gc.ca/lims" 
         lims:id="114997" 
         lims:current-date="2026-03-02">
  <Identification>
    <ShortTitle>Criminal Code</ShortTitle>
    <Chapter>
      <ConsolidatedNumber official="yes">C-46</ConsolidatedNumber>
    </Chapter>
  </Identification>
  <Body>
    <Section>
      <Label>1</Label>
      <MarginalNote>Short title</MarginalNote>
      <Text>This Act may be cited as the Criminal Code.</Text>
    </Section>
    <Section>
      <Label>2</Label>
      <MarginalNote>Definitions</MarginalNote>
      <Text>In this Act, ...</Text>
    </Section>
  </Body>
</Statute>
"""
        record = parse_statute_xml(xml)
        
        assert record is not None
        assert record["statute_id"] == "114997"
        assert record["short_title"] == "Criminal Code"
        assert record["consolidated_number"] == "C-46"
        assert len(record["sections"]) == 2
        assert record["sections"][0]["label"] == "1"
        assert "Criminal Code" in record["sections"][0]["text"]

    def test_parse_statute_xml_nested_text_and_subsections(self):
        with (_FIXTURES / "sor-2002-227_sample.xml").open("rb") as f:
            xml = f.read()

        record = parse_statute_xml(xml)
        assert record["chapter_or_instrument_number"] == "SOR/2002-227"
        assert len(record["sections"]) == 3
        section_one = next(s for s in record["sections"] if s["path"] == "section:1")
        assert "food and drugs" in section_one["text"].lower()
        subsection = next(
            s for s in record["sections"] if s.get("subsection_label") == "(1)"
        )
        assert "legend" in subsection["text"].lower()
        assert subsection["section_key"].startswith("justice-sec-")

    def test_parse_statute_xml_invalid_root_fails_closed(self):
        with pytest.raises(ValueError):
            parse_statute_xml(b"<BadRoot />")


class TestFixtures:
    """Tests using Criminal Code fixtures."""
    
    def test_parse_legis_fixture(self):
        """Parse Legis.xml fixture."""
        with (_FIXTURES / "legis_sample.xml").open("rb") as f:
            xml = f.read()
        
        records = parse_legis_index(xml)
        
        # Should have 2 records (eng + fra)
        assert len(records) == 2
        
        # First should be English
        assert records[0]["unique_id"] == "C-46"
        assert records[0]["language"] == "eng"
        assert records[0]["title"] == "Criminal Code"
        assert records[0]["law_type"] == "Act"
        
        # Second should be French
        assert records[1]["unique_id"] == "C-46"
        assert records[1]["language"] == "fra"
        assert records[1]["title"] == "Code criminel"
    
    def test_parse_criminal_code_fixture(self):
        """Parse Criminal Code statute fixture."""
        with (_FIXTURES / "c-46_sample.xml").open("rb") as f:
            xml = f.read()
        
        record = parse_statute_xml(xml)
        
        assert record is not None
        assert record["statute_id"] == "114997"
        assert record["short_title"] == "Criminal Code"
        assert record["long_title"] == "An Act respecting the Criminal Law"
        assert record["consolidated_number"] == "C-46"
        assert record["current_date"] == "2026-03-02"
        
        # Should have 2 sections
        assert len(record["sections"]) == 2
        
        # First section
        assert record["sections"][0]["label"] == "1"
        assert record["sections"][0]["marginal_note"] == "Short title"
        assert "Criminal Code" in record["sections"][0]["text"]
        
        # Second section
        assert record["sections"][1]["label"] == "2"
        assert record["sections"][1]["marginal_note"] == "Definitions"
        assert "bodily harm" in record["sections"][1]["text"]

    def test_parser_handles_missing_optional_metadata(self):
        xml = b"""<?xml version=\"1.0\"?>
<Statute xmlns:lims=\"http://justice.gc.ca/lims\" lims:id=\"abc\">
  <Identification>
    <ShortTitle>Sample Law</ShortTitle>
  </Identification>
  <Body>
    <Section>
      <Label>1</Label>
      <Text>Sample text.</Text>
    </Section>
  </Body>
</Statute>
"""
        record = parse_statute_xml(xml)
        assert record["long_title"] is None
        assert record["citation"] is None
        assert record["current_date"] is None
        assert len(record["sections"]) == 1

    def test_parser_section_keys_are_deterministic(self):
        with (_FIXTURES / "c-46_sample.xml").open("rb") as f:
            xml = f.read()

        first = parse_statute_xml(xml)
        second = parse_statute_xml(xml)
        first_keys = [s["section_key"] for s in first["sections"]]
        second_keys = [s["section_key"] for s in second["sections"]]
        assert first_keys == second_keys
    
    def test_validate_legis_fixture(self):
        """Validate Legis.xml fixture schema."""
        with (_FIXTURES / "legis_sample.xml").open("rb") as f:
            xml = f.read()
        
        assert validate_index_xml(xml) is True
    
    def test_validate_criminal_code_fixture(self):
        """Validate Criminal Code statute fixture schema."""
        with (_FIXTURES / "c-46_sample.xml").open("rb") as f:
            xml = f.read()
        
        assert validate_statute_xml(xml, "C-46") is True

    def test_validate_statute_fixture_with_subsection_text(self):
        with (_FIXTURES / "sor-2002-227_sample.xml").open("rb") as f:
            xml = f.read()

        assert validate_statute_xml(xml, "SOR-2002-227") is True
