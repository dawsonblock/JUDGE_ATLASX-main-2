"""Saskatchewan law adapter from King's Printer / Freelaw.

Official source: https://publications.saskatchewan.ca
Freelaw provides free online access to current Government of Saskatchewan legislation.

Priority laws for Judge Atlas:
- Saskatchewan Police Act
- Saskatchewan Correctional Services Act
- Saskatchewan Victims of Crime Act
- Provincial court-related regulations
- Policing-related provincial laws
- Municipal/government law context

Schema:
- jurisdiction: CA-SK
- source: Saskatchewan King's Printer / Freelaw
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

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
import lxml.html

# Product IDs and HTML format IDs for the three priority acts
# Source: Saskatchewan ePublications (publications.saskatchewan.ca)
_SK_ACTS: dict[str, dict[str, Any]] = {
    "Saskatchewan Police Act": {
        "product_id": 10314,
        "html_format_id": 10976,
        "chapter": "S.S. 2018, c. P-15.2",
        "sections": ["2", "5"],
    },
    "Saskatchewan Correctional Services Act": {
        "product_id": 9568,
        "html_format_id": 9697,
        "chapter": "S.S. 2012, c. C-37.1",
        "sections": ["3"],
    },
    "Saskatchewan Victims of Crime Act": {
        "product_id": 10902,
        "html_format_id": 11149,
        "chapter": "S.S. 1995, c. V-6",
        "sections": ["2"],
    },
}


@dataclass
class SaskatchewanLawSection:
    """A section of Saskatchewan provincial law.

    IMPORTANT: When is_stub=True, this is placeholder/hard-coded content,
    NOT fetched from official sources. Stub content must never be marked
    as trusted or used as authoritative legal text.
    """

    jurisdiction: str = "CA-SK"
    source: str = "Saskatchewan King's Printer"
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


class SaskatchewanLawAdapter:
    """Adapter for Saskatchewan King's Printer / Freelaw.

    Official source for Saskatchewan provincial legislation.
    """

    BASE_URL = "https://publications.saskatchewan.ca"
    FREELAW_URL = f"{BASE_URL}/#laws-and-regulations"

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

    def _fetch_act_sections(
        self,
        act_name: str,
    ) -> list[SaskatchewanLawSection]:
        """Fetch sections for a Saskatchewan act from ePublications.

        Args:
            act_name: Key from _SK_ACTS dict

        Returns:
            List of SaskatchewanLawSection with is_stub=False on success,
            empty list on HTTP error or unknown act.
        """
        meta = _SK_ACTS.get(act_name)
        if meta is None:
            return []

        product_id = meta["product_id"]
        fmt_id = meta["html_format_id"]
        chapter = meta["chapter"]
        target_sections: list[str] = meta["sections"]

        url = f"{self.BASE_URL}/api/v1/products/{product_id}/formats/{fmt_id}"
        try:
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return []

        raw_text = response.text
        raw_hash = self._compute_hash(raw_text)
        doc = lxml.html.fromstring(raw_text)

        sections: list[SaskatchewanLawSection] = []
        for sec_num in target_sections:
            # Look for a section heading that matches the section number
            heading = ""
            heading_nodes = doc.cssselect(
                f"[id='{sec_num}'], [id='sec_{sec_num}'], [data-section='{sec_num}']"
            )
            if heading_nodes:
                heading = heading_nodes[0].text_content().strip()

            # Fall back: grab any strong/h tag near the section anchor
            if not heading:
                for tag in ("h3", "h4", "strong"):
                    nodes = doc.cssselect(tag)
                    if nodes:
                        heading = nodes[0].text_content().strip()
                        break

            # Extract full page text as section text (entire statute HTML)
            full_text = doc.cssselect("main, article, body") or [doc]
            section_text = full_text[0].text_content().strip()

            sections.append(
                SaskatchewanLawSection(
                    jurisdiction="CA-SK",
                    source="Saskatchewan King's Printer",
                    law_title=act_name,
                    law_type="act",
                    chapter=chapter,
                    section_number=sec_num,
                    section_heading=heading,
                    section_text=section_text,
                    language="en",
                    source_url=url,
                    consolidation_date=date.today(),
                    raw_hash=raw_hash,
                    is_stub=False,
                )
            )

        return sections

    def fetch_police_act_sections(self) -> list[SaskatchewanLawSection]:
        """Fetch Saskatchewan Police Act sections.

        Returns:
            List of SaskatchewanLawSection objects
        """
        return self._fetch_act_sections("Saskatchewan Police Act")

    def fetch_correctional_services_sections(self) -> list[SaskatchewanLawSection]:
        """Fetch Saskatchewan Correctional Services Act sections.

        Returns:
            List of SaskatchewanLawSection objects
        """
        return self._fetch_act_sections("Saskatchewan Correctional Services Act")

    def fetch_victims_of_crime_sections(self) -> list[SaskatchewanLawSection]:
        """Fetch Saskatchewan Victims of Crime Act sections.

        Returns:
            List of SaskatchewanLawSection objects
        """
        return self._fetch_act_sections("Saskatchewan Victims of Crime Act")

    def get_law_by_citation(
        self,
        citation: str,
    ) -> SaskatchewanLawSection | None:
        """Lookup law by citation.

        Supports citations like:
        - "Saskatchewan Police Act, s. 5"
        - "Police Act, s. 2"

        Args:
            citation: Legal citation string

        Returns:
            SaskatchewanLawSection if found, None otherwise
        """
        citation_lower = citation.lower()

        if "police" in citation_lower:
            sections = self.fetch_police_act_sections()
            import re

            match = re.search(r"s\.?\s*(\d+[a-z]?)", citation_lower)
            if match:
                section_num = match.group(1)
                for section in sections:
                    if section.section_number == section_num:
                        return section
            # Return first section if no specific match
            if sections:
                return sections[0]

        elif "correctional" in citation_lower:
            sections = self.fetch_correctional_services_sections()
            if sections:
                return sections[0]

        elif "victims" in citation_lower:
            sections = self.fetch_victims_of_crime_sections()
            if sections:
                return sections[0]

        return None

    def link_event_to_law(
        self,
        event_type: str,
        event_description: str,
    ) -> list[SaskatchewanLawSection]:
        """Suggest relevant Saskatchewan law sections for an event.

        Args:
            event_type: Type of court event
            event_description: Description of the event

        Returns:
            List of relevant SaskatchewanLawSection objects
        """
        relevant_laws = []

        desc_lower = event_description.lower()

        # Police matters
        if any(term in desc_lower for term in ["police", "officer", "detention"]):
            police_sections = self.fetch_police_act_sections()
            relevant_laws.extend(police_sections)

        # Corrections / probation
        if any(
            term in desc_lower
            for term in ["correctional", "probation", "sentence", "custody"]
        ):
            correctional_sections = self.fetch_correctional_services_sections()
            relevant_laws.extend(correctional_sections)

        # Victims
        if any(term in desc_lower for term in ["victim", "restitution"]):
            victim_sections = self.fetch_victims_of_crime_sections()
            relevant_laws.extend(victim_sections)

        return relevant_laws

    def get_priority_laws(self) -> list[SaskatchewanLawSection]:
        """Get all priority Saskatchewan laws for Judge Atlas.

        Returns:
            List of key Saskatchewan law sections
        """
        all_sections = []

        all_sections.extend(self.fetch_police_act_sections())
        all_sections.extend(self.fetch_correctional_services_sections())
        all_sections.extend(self.fetch_victims_of_crime_sections())

        return all_sections
