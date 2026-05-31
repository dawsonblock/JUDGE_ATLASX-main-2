"""Parser for Justice Canada law XML documents."""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def parse_legis_index(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse master index (Legis.xml)."""
    root = ET.fromstring(xml_bytes)
    records: list[dict[str, Any]] = []
    
    for act_elem in root.findall(".//Act"):
        record = _extract_law_metadata(act_elem, "Act")
        if record:
            records.append(record)
    
    for reg_elem in root.findall(".//Regulation"):
        record = _extract_law_metadata(reg_elem, "Regulation")
        if record:
            records.append(record)
    
    return records


def parse_statute_xml(xml_bytes: bytes) -> dict[str, Any] | None:
    """Parse individual statute XML."""
    root = ET.fromstring(xml_bytes)
    
    lims_ns = "{http://justice.gc.ca/lims}"
    statute_id = root.get(f"{lims_ns}id", "UNKNOWN")
    current_date = root.get(f"{lims_ns}current-date")
    
    identification = root.find("Identification")
    short_title = None
    long_title = None
    consolidated_number = None
    
    if identification is not None:
        st_elem = identification.find("ShortTitle")
        short_title = st_elem.text if st_elem is not None else None
        
        lt_elem = identification.find("LongTitle")
        long_title = lt_elem.text if lt_elem is not None else None
        
        chapter = identification.find("Chapter")
        if chapter is not None:
            cn_elem = chapter.find("ConsolidatedNumber")
            consolidated_number = cn_elem.text if cn_elem is not None else None
    
    sections = []
    body = root.find("Body")
    if body is not None:
        sections = _extract_sections(body)
    
    return {
        "statute_id": statute_id,
        "short_title": short_title,
        "long_title": long_title,
        "consolidated_number": consolidated_number,
        "current_date": current_date,
        "sections": sections,
    }


def _extract_law_metadata(elem: ET.Element, law_type: str) -> dict[str, Any] | None:
    """Extract metadata from Act or Regulation element."""
    unique_id = elem.findtext("UniqueId")
    language = elem.findtext("Language")
    title = elem.findtext("Title")
    link_to_xml = elem.findtext("LinkToXML")
    link_to_html_toc = elem.findtext("LinkToHTMLToC")
    official_number = elem.findtext("OfficialNumber")
    current_to_date = elem.findtext("CurrentToDate")
    
    if not unique_id or not language or not title or not link_to_xml:
        return None
    
    return {
        "unique_id": unique_id,
        "language": language,
        "title": title,
        "law_type": law_type,
        "official_number": official_number,
        "link_to_xml": link_to_xml,
        "link_to_html_toc": link_to_html_toc,
        "current_to_date": current_to_date,
    }


def _extract_sections(body_elem: ET.Element) -> list[dict[str, Any]]:
    """Extract sections from Body."""
    sections: list[dict[str, Any]] = []
    
    for section_elem in body_elem.findall(".//Section"):
        label = section_elem.findtext("Label")
        text = section_elem.findtext("Text")
        marginal_note = section_elem.findtext("MarginalNote")
        
        if not label or not text:
            continue
        
        section_record: dict[str, Any] = {
            "label": label,
            "text": text,
            "marginal_note": marginal_note,
        }
        
        sections.append(section_record)
    
    return sections
