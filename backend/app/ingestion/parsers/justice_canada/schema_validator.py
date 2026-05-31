"""Structural validator for Justice Canada legislation XML."""

from __future__ import annotations

from xml.etree import ElementTree as ET


class SchemaValidationError(Exception):
    """Raised when Justice Canada XML fails structural validation."""


def validate_index_xml(xml_bytes: bytes) -> bool:
    """Validate the Legis.xml index format.

    This performs structural validation only (not full DTD validation).
    """
    root = ET.fromstring(xml_bytes)
    if root.tag != "ActsRegsList":
        raise SchemaValidationError("Root element must be ActsRegsList")

    acts = root.findall("./Acts/Act")
    regulations = root.findall("./Regulations/Regulation")
    if not acts and not regulations:
        raise SchemaValidationError("ActsRegsList must include Act or Regulation entries")

    for item in acts + regulations:
        for field in ("UniqueId", "Language", "Title", "LinkToXML"):
            if not (item.findtext(field) or "").strip():
                raise SchemaValidationError(f"Act/Regulation missing required field {field}")
    return True


def validate_statute_xml(xml_bytes: bytes, statute_id: str) -> bool:
    """Validate statute/regulation document shape.

    This performs structural validation only (not full DTD validation).
    """
    root = ET.fromstring(xml_bytes)
    if root.tag != "Statute":
        raise SchemaValidationError("Root element must be Statute")

    lims_ns = "{http://justice.gc.ca/lims}"
    if f"{lims_ns}id" not in root.attrib:
        raise SchemaValidationError(f"Missing lims:id in {statute_id}")

    identification = root.find("Identification")
    body = root.find("Body")
    if identification is None:
        raise SchemaValidationError(f"Missing Identification in {statute_id}")
    if body is None:
        raise SchemaValidationError(f"Missing Body in {statute_id}")

    has_short_title = bool((identification.findtext("ShortTitle") or "").strip())
    has_long_title = bool((identification.findtext("LongTitle") or "").strip())
    if not (has_short_title or has_long_title):
        raise SchemaValidationError(f"Missing ShortTitle/LongTitle in {statute_id}")

    sections = body.findall(".//Section")
    if not sections:
        raise SchemaValidationError(f"Body contains no Section in {statute_id}")

    for section in sections:
        label = (section.findtext("Label") or "").strip()
        if not label:
            raise SchemaValidationError(f"Section missing Label in {statute_id}")

        has_section_text = any((text_elem.text or "").strip() for text_elem in section.findall("Text"))
        has_subsection_text = any(
            any((text_elem.text or "").strip() for text_elem in subsection.findall("Text"))
            for subsection in section.findall("Subsection")
        )
        if not (has_section_text or has_subsection_text):
            raise SchemaValidationError(f"Section {label} missing Text in {statute_id}")

    return True
