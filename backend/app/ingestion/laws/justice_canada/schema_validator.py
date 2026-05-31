"""Schema validator for Justice Canada law XML."""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Schema validation failed."""
    pass


def validate_index_xml(xml_bytes: bytes) -> bool:
    """Validate Legis.xml structure."""
    root = ET.fromstring(xml_bytes)
    
    if root.tag != "ActsRegsList":
        raise SchemaValidationError(f"Root element must be 'ActsRegsList'")
    
    acts = root.findall(".//Act")
    regs = root.findall(".//Regulation")
    
    if not acts and not regs:
        raise SchemaValidationError("Legis.xml contains no Act or Regulation")
    
    first_item = acts[0] if acts else regs[0]
    for field in ["UniqueId", "Language", "Title", "LinkToXML"]:
        if first_item.findtext(field) is None:
            raise SchemaValidationError(f"Act/Regulation missing required field '{field}'")
    
    return True


def validate_statute_xml(xml_bytes: bytes, statute_id: str) -> bool:
    """Validate statute XML."""
    root = ET.fromstring(xml_bytes)
    
    if root.tag != "Statute":
        raise SchemaValidationError(f"Root element must be 'Statute'")
    
    lims_ns = "{http://justice.gc.ca/lims}"
    for attr in [f"{lims_ns}id", f"{lims_ns}current-date"]:
        if attr not in root.attrib:
            raise SchemaValidationError(f"Missing required attribute in {statute_id}")
    
    if root.find("Identification") is None:
        raise SchemaValidationError(f"Missing Identification in {statute_id}")
    
    if root.find("Body") is None:
        raise SchemaValidationError(f"Missing Body in {statute_id}")
    
    identification = root.find("Identification")
    if identification.find("ShortTitle") is None and identification.find("LongTitle") is None:
        raise SchemaValidationError(f"Missing ShortTitle or LongTitle in {statute_id}")
    
    body = root.find("Body")
    sections = body.findall("Section")
    if not sections:
        raise SchemaValidationError(f"Body contains no Section in {statute_id}")
    
    first_section = sections[0]
    if first_section.find("Label") is None or first_section.find("Text") is None:
        raise SchemaValidationError(f"Section missing Label or Text in {statute_id}")
    
    return True
