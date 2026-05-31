"""Parser for Justice Canada legislation XML documents."""

from __future__ import annotations

import hashlib
from typing import Any
from xml.etree import ElementTree as ET

_LIMS_NS = "{http://justice.gc.ca/lims}"


def parse_legis_index(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse `ActsRegsList` index XML into deterministic instrument metadata."""
    root = ET.fromstring(xml_bytes)
    if root.tag != "ActsRegsList":
        raise ValueError("Expected ActsRegsList root")

    records: list[dict[str, Any]] = []
    records.extend(_parse_index_collection(root, "Acts", "Act", "Act"))
    records.extend(_parse_index_collection(root, "Regulations", "Regulation", "Regulation"))
    return records


def parse_statute_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse a statute/regulation XML payload.

    The parser is structural and deterministic; it does not claim full DTD coverage.
    """
    root = ET.fromstring(xml_bytes)
    if root.tag != "Statute":
        raise ValueError("Expected Statute root")

    identification = root.find("Identification")
    body = root.find("Body")
    if identification is None or body is None:
        raise ValueError("Statute document missing Identification or Body")

    short_title = _clean_text(_node_text(identification.find("ShortTitle")))
    long_title = _clean_text(_node_text(identification.find("LongTitle")))

    citation = _clean_text(_node_text(identification.find("Citation")))
    chapter_or_instrument_number = _clean_text(
        _node_text(identification.find("Chapter/ConsolidatedNumber"))
        or _node_text(identification.find("InstrumentNumber"))
        or _node_text(identification.find("OfficialNumber"))
    )

    sections = _extract_sections(body)

    return {
        "statute_id": root.get(f"{_LIMS_NS}id", "UNKNOWN"),
        "short_title": short_title,
        "long_title": long_title,
        "citation": citation,
        "chapter_or_instrument_number": chapter_or_instrument_number,
        "consolidated_number": _clean_text(_node_text(identification.find("Chapter/ConsolidatedNumber"))),
        "current_date": root.get(f"{_LIMS_NS}current-date"),
        "last_amended_date": root.get(f"{_LIMS_NS}lastAmendedDate"),
        "in_force_start_date": root.get(f"{_LIMS_NS}inforce-start-date"),
        "sections": sections,
    }


def _parse_index_collection(
    root: ET.Element,
    container_tag: str,
    item_tag: str,
    instrument_type: str,
) -> list[dict[str, Any]]:
    collection = root.find(container_tag)
    if collection is None:
        return []

    records: list[dict[str, Any]] = []
    for node in collection.findall(item_tag):
        unique_id = _clean_text(node.findtext("UniqueId"))
        language = _clean_text(node.findtext("Language"))
        title = _clean_text(node.findtext("Title"))
        link_to_xml = _clean_text(node.findtext("LinkToXML"))
        if not unique_id or not language or not title or not link_to_xml:
            continue

        records.append(
            {
                "unique_id": unique_id,
                "language": language,
                "title": title,
                "instrument_type": instrument_type,
                "law_type": instrument_type,
                "official_number": _clean_text(node.findtext("OfficialNumber")),
                "current_to_date": _clean_text(node.findtext("CurrentToDate")),
                "link_to_xml": link_to_xml,
                "link_to_html_toc": _clean_text(node.findtext("LinkToHTMLToC")),
            }
        )
    return records


def _extract_sections(body_elem: ET.Element) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section in body_elem.findall(".//Section"):
        label = _clean_text(_node_text(section.find("Label")))
        if not label:
            continue

        source_xml_node_id = section.get(f"{_LIMS_NS}id")
        marginal_note = _clean_text(_node_text(section.find("MarginalNote")))

        text_nodes = section.findall("Text")
        subsection_nodes = section.findall("Subsection")

        section_path = f"section:{label}"
        section_text = "\n".join(_clean_text(_node_text(node)) for node in text_nodes if _clean_text(_node_text(node)))
        if not section_text and subsection_nodes:
            section_text = "\n".join(
                _clean_text(_node_text(text_elem))
                for subsection in subsection_nodes
                for text_elem in subsection.findall("Text")
                if _clean_text(_node_text(text_elem))
            )
        if section_text:
            sections.append(
                {
                    "label": label,
                    "section_label": label,
                    "subsection_label": None,
                    "marginal_note": marginal_note,
                    "text": section_text,
                    "path": section_path,
                    "source_xml_node_id": source_xml_node_id,
                    "section_key": _section_key(section_path, label, None, source_xml_node_id),
                }
            )

        for subsection in subsection_nodes:
            sublabel = _clean_text(_node_text(subsection.find("Label")))
            subsection_path = section_path
            if sublabel:
                subsection_path = f"{section_path}/subsection:{sublabel}"
            subsection_text_nodes = subsection.findall("Text")
            subsection_text = "\n".join(
                _clean_text(_node_text(node)) for node in subsection_text_nodes if _clean_text(_node_text(node))
            )
            if not subsection_text:
                continue
            sections.append(
                {
                    "label": label,
                    "section_label": label,
                    "subsection_label": sublabel,
                    "marginal_note": marginal_note,
                    "text": subsection_text,
                    "path": subsection_path,
                    "source_xml_node_id": subsection.get(f"{_LIMS_NS}id") or source_xml_node_id,
                    "section_key": _section_key(
                        subsection_path,
                        label,
                        sublabel,
                        subsection.get(f"{_LIMS_NS}id") or source_xml_node_id,
                    ),
                }
            )

    return sections


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    return compact or None


def _section_key(path: str, section_label: str, subsection_label: str | None, node_id: str | None) -> str:
    stable = "|".join([path, section_label, subsection_label or "", node_id or ""]) 
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
    return f"justice-sec-{digest}"
