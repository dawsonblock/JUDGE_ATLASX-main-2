"""Justice Laws Website XML adapter for federal Canadian law.

Official source: https://laws.justice.gc.ca

Provides consolidated federal Acts and regulations in XML format.
Federal consolidated Acts and regulations are official as of June 1, 2009.

Schema:
- jurisdiction: CA-FED
- source: Justice Laws
- law_title
- law_type: act | regulation
- chapter
- section_number
- section_heading
- section_text
- language
- source_url
- consolidation_date
- raw_hash
"""

# DEPRECATED: This module is the LEGACY ingestion path for Justice Canada XML.
# It is NOT used by the current ingestion pipeline.
# Canonical adapter:  backend/app/ingestion/source_adapters/laws_justice_xml.py
# Canonical parser:   backend/app/ingestion/laws/justice_canada/ (if present)
# Source registry key: laws_justice_xml
# Do NOT add new ingestion logic here. This file is retained for reference only.

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any

import lxml.html
import httpx

# Act code → chapter mapping
_ACT_CHAPTERS: dict[str, str] = {
    "C-46": "R.S.C., 1985, c. C-46",
    "Y-1.5": "S.C. 2002, c. 1",
}

# Short act name → act code (for URL construction)
_ACT_CODES: dict[str, str] = {
    "Criminal Code": "C-46",
    "Youth Criminal Justice Act": "Y-1.5",
    "YCJA": "Y-1.5",
}

# Act code → priority sections to fetch
_PRIORITY_SECTIONS: dict[str, list[str]] = {
    "C-46": ["515", "718", "753"],
    "Y-1.5": ["3"],
}


@dataclass
class LawSection:
    """A section of Canadian federal law.

    IMPORTANT: When is_stub=True, this is placeholder/hard-coded content,
    NOT fetched from official sources. Stub content must never be marked
    as trusted or used as authoritative legal text.
    """

    jurisdiction: str = "CA-FED"
    source: str = "Justice Laws"
    law_title: str = ""
    law_type: str = ""  # "act" | "regulation"
    chapter: str = ""
    section_number: str = ""
    section_heading: str = ""
    section_text: str = ""
    language: str = "en"
    source_url: str = ""
    consolidation_date: date | None = None
    raw_hash: str = ""
    is_stub: bool = True  # True for hard-coded, False for fetched from source


class JusticeLawsAdapter:
    """Adapter for Justice Laws Website XML data.

    Official source for Canadian federal legislation.
    """

    BASE_URL = "https://laws.justice.gc.ca"
    XML_INDEX_URL = f"{BASE_URL}/eng/XML/LIndex/"

    def __init__(self, client: httpx.Client | None = None):
        """Initialize adapter.

        Args:
            client: HTTP client (creates default if None)
        """
        self.client = client or httpx.Client(timeout=30.0)

    def _compute_hash(self, content: str | bytes) -> str:
        """Compute SHA256 hash of content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def _fetch_section_html(
        self,
        act_code: str,
        section_num: str,
        act_name: str,
        chapter: str,
    ) -> LawSection | None:
        """Fetch a single section HTML page and parse it.

        Args:
            act_code: Justice Laws act code, e.g. "C-46"
            section_num: Section number, e.g. "515"
            act_name: Display name of the act
            chapter: Chapter citation

        Returns:
            LawSection with is_stub=False on success, None on HTTP error.
        """
        url = f"{self.BASE_URL}/eng/acts/{act_code}/section-{section_num}.html"
        try:
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        raw_text = response.text
        doc = lxml.html.fromstring(raw_text)

        # Extract marginal note (section heading)
        heading = ""
        for selector in (".marginal-note", ".MarginalNote", "p.marginalNote"):
            nodes = doc.cssselect(selector)
            if nodes:
                heading = nodes[0].text_content().strip()
                break

        # Extract main section text from the provision area
        section_text = ""
        for selector in ("section", "main", "#wb-main-in", "body"):
            nodes = doc.cssselect(selector)
            if nodes:
                section_text = nodes[0].text_content().strip()
                break

        raw_hash = self._compute_hash(raw_text)

        return LawSection(
            jurisdiction="CA-FED",
            source="Justice Laws",
            law_title=act_name,
            law_type="act",
            chapter=chapter,
            section_number=section_num,
            section_heading=heading,
            section_text=section_text,
            language="en",
            source_url=url,
            consolidation_date=date.today(),
            raw_hash=raw_hash,
            is_stub=False,
        )

    def fetch_law_index(self) -> list[dict[str, Any]]:
        """Fetch list of available laws from XML index.

        Returns:
            List of law metadata dictionaries
        """
        try:
            response = self.client.get(self.XML_INDEX_URL)
            response.raise_for_status()
            # Parse XML index - simplified for prototype
            # In production, parse full XML structure
            return []
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch law index: {e}") from e

    def fetch_act_sections(
        self,
        act_name: str,
        chapter: str | None = None,
    ) -> list[LawSection]:
        """Fetch sections of a specific federal Act.

        Priority laws for Judge Atlas:
        - Criminal Code (R.S.C., 1985, c. C-46)
        - Youth Criminal Justice Act (S.C. 2002, c. 1)
        - Controlled Drugs and Substances Act (S.C. 1996, c. 19)
        - Corrections and Conditional Release Act (S.C. 1992, c. 20)
        - Canada Evidence Act (R.S.C., 1985, c. C-5)
        - Canadian Victims Bill of Rights (S.C. 2015, c. 13)

        Args:
            act_name: Short name of the Act (e.g., "Criminal Code")
            chapter: Chapter reference if known

        Returns:
            List of LawSection objects
        """
        act_code = _ACT_CODES.get(act_name)
        if act_code is None:
            return []

        resolved_chapter = chapter or _ACT_CHAPTERS.get(act_code, "")
        target_sections = _PRIORITY_SECTIONS.get(act_code, [])

        sections: list[LawSection] = []
        for section_num in target_sections:
            result = self._fetch_section_html(
                act_code=act_code,
                section_num=section_num,
                act_name=act_name,
                chapter=resolved_chapter,
            )
            if result is not None:
                sections.append(result)

        return sections

    def fetch_youth_criminal_justice_sections(self) -> list[LawSection]:
        """Fetch Youth Criminal Justice Act sections.

        Returns:
            List of LawSection objects for YCJA
        """
        return self.fetch_act_sections("Youth Criminal Justice Act")

    def get_law_by_citation(
        self,
        citation: str,
    ) -> LawSection | None:
        """Lookup law by citation.

        Supports citations like:
        - "Criminal Code, s. 515"
        - "Criminal Code, s. 718(1)"
        - "YCJA, s. 3"

        Args:
            citation: Legal citation string

        Returns:
            LawSection if found, None otherwise
        """
        # Parse citation
        citation_lower = citation.lower()

        if "criminal code" in citation_lower:
            # Extract section number
            import re

            match = re.search(r"s\.?\s*(\d+[a-z]?)", citation_lower)
            if match:
                section_num = match.group(1)
                sections = self.fetch_act_sections("Criminal Code")
                for section in sections:
                    if section.section_number == section_num:
                        return section

        elif "ycja" in citation_lower or "youth" in citation_lower:
            sections = self.fetch_youth_criminal_justice_sections()
            if sections:
                return sections[0]

        return None

    def link_event_to_law(
        self,
        event_type: str,
        event_description: str,
    ) -> list[LawSection]:
        """Suggest relevant law sections for an event.

        Args:
            event_type: Type of court event
            event_description: Description of the event

        Returns:
            List of relevant LawSection objects
        """
        relevant_laws = []

        desc_lower = event_description.lower()

        # Bail / release
        if any(term in desc_lower for term in ["bail", "release", "detention", "515"]):
            bail_section = self.get_law_by_citation("Criminal Code, s. 515")
            if bail_section:
                relevant_laws.append(bail_section)

        # Sentencing
        if any(term in desc_lower for term in ["sentence", "sentencing", "718"]):
            sentencing_section = self.get_law_by_citation("Criminal Code, s. 718")
            if sentencing_section:
                relevant_laws.append(sentencing_section)

        # Dangerous offender
        if any(term in desc_lower for term in ["dangerous offender", "753"]):
            do_section = self.get_law_by_citation("Criminal Code, s. 753")
            if do_section:
                relevant_laws.append(do_section)

        # Youth matters
        if any(term in desc_lower for term in ["youth", "young person", "ycja"]):
            youth_sections = self.fetch_youth_criminal_justice_sections()
            relevant_laws.extend(youth_sections)

        return relevant_laws
