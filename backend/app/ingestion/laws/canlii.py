"""CanLII API adapter for Canadian case law.

Official source: https://api.canlii.org

CanLII (Canadian Legal Information Institute) provides free online access to
Canadian court decisions, tribunal decisions, and legislation.  This adapter
targets the CanLII REST API v1 which covers decisions from all major Canadian
federal and provincial courts.

Requires the environment variable ``JTA_CANLII_API_KEY`` (or settings field
``canlii_api_key``) to be set.  API keys are available at
https://api.canlii.org/register.

Priority databases targeted by Judge Atlas:
- ``csc-scc``  — Supreme Court of Canada
- ``onca``     — Ontario Court of Appeal
- ``bcca``     — British Columbia Court of Appeal
- ``abca``     — Alberta Court of Appeal
- ``qcca``     — Court of Appeal of Quebec

Schema output fields
--------------------
- jurisdiction : str   ISO-style e.g. "CA-SCC", "CA-ON"
- source        : str  "CanLII"
- law_title     : str  Case style of cause
- law_type      : str  "decision"
- chapter       : str  Neutral citation (e.g. "2024 SCC 12")
- section_number: str  "" (not applicable for case decisions)
- section_heading: str  Style of cause (same as law_title)
- section_text  : str  Full text of the decision (may be empty if unavailable)
- language      : str  "en" or "fr"
- source_url    : str  Canonical CanLII URL
- consolidation_date : date | None  Decision date
- raw_hash      : str  SHA-256 of raw API response bytes
- is_stub       : bool True if text not fetched; False when fully retrieved
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

log = logging.getLogger(__name__)

_CANLII_BASE = "https://api.canlii.org/v1"

# Canonical database IDs → jurisdiction codes used in Atlas schema
_DB_TO_JURISDICTION: dict[str, str] = {
    "csc-scc": "CA-SCC",
    "onca": "CA-ON",
    "bcca": "CA-BC",
    "abca": "CA-AB",
    "qcca": "CA-QC",
    "skca": "CA-SK",
    "mbca": "CA-MB",
    "nsca": "CA-NS",
    "nbca": "CA-NB",
    "nlca": "CA-NL",
    "peca": "CA-PE",
    "ykca": "CA-YT",
    "nwtca": "CA-NT",
    "nuca": "CA-NU",
    "fca-caf": "CA-FED",
}

# Priority databases ordered by relevance for Judge Atlas
PRIORITY_DATABASES: list[str] = [
    "csc-scc",
    "onca",
    "bcca",
    "abca",
    "qcca",
    "skca",
    "fca-caf",
]


@dataclass
class CanLIILawSection:
    """A single Canadian case decision retrieved from CanLII.

    IMPORTANT: When ``is_stub=True`` this is placeholder or partially-fetched
    content, NOT yet confirmed as authoritative text.  Stub content must never
    be marked as trusted or used without subsequent full retrieval.
    """

    jurisdiction: str = ""
    source: str = "CanLII"
    law_title: str = ""  # Style of cause
    law_type: str = "decision"
    chapter: str = ""  # Neutral citation
    section_number: str = ""  # Not applicable for case decisions
    section_heading: str = ""  # Style of cause (mirrors law_title)
    section_text: str = ""  # Full decision text
    language: str = "en"
    source_url: str = ""
    consolidation_date: date | None = None  # Decision date
    raw_hash: str = ""
    is_stub: bool = True  # False only after full text is retrieved


class CanLIIAdapter:
    """Adapter for the CanLII REST API v1.

    Retrieves case metadata and optionally full text for Canadian court
    decisions.  Requires an API key provided via ``JTA_CANLII_API_KEY``
    environment variable or passed directly to the constructor.

    Args:
        api_key: CanLII API key.  Falls back to ``JTA_CANLII_API_KEY`` env var.
        language: Preferred language for requests; ``"en"`` or ``"fr"``.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str | None = None,
        language: str = "en",
        timeout: float = 30.0,
    ) -> None:
        if api_key is not None:
            self._api_key = api_key
        else:
            from app.core.config import get_settings  # noqa: PLC0415

            self._api_key = get_settings().canlii_api_key or ""
        self._language = language
        self._timeout = timeout
        self.errors: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_case(
        self,
        database_id: str,
        case_id: str,
    ) -> CanLIILawSection:
        """Fetch metadata and full text for a single case.

        Args:
            database_id: CanLII database identifier (e.g. ``"csc-scc"``).
            case_id:     CanLII case identifier (e.g. ``"2024scc12"``).

        Returns:
            :class:`CanLIILawSection` with ``is_stub=False`` on success, or
            ``is_stub=True`` populated only with error information on failure.
        """
        metadata = self._fetch_case_metadata(database_id, case_id)
        if metadata is None:
            stub = CanLIILawSection(
                jurisdiction=_DB_TO_JURISDICTION.get(database_id, database_id.upper()),
                law_title=case_id,
                is_stub=True,
            )
            return stub

        section = self._metadata_to_section(database_id, metadata)
        text = self._fetch_case_text(database_id, case_id)
        if text:
            section.section_text = text
            section.is_stub = False

        return section

    def fetch_recent_cases(
        self,
        database_id: str,
        *,
        result_count: int = 10,
        offset: int = 0,
    ) -> list[CanLIILawSection]:
        """Fetch a page of recently published cases from *database_id*.

        Only metadata is retrieved (``is_stub=True``); call
        :meth:`fetch_case` for full text.

        Args:
            database_id:  CanLII database identifier.
            result_count: Number of cases to retrieve (max 100 per API docs).
            offset:       Pagination offset.

        Returns:
            List of :class:`CanLIILawSection` instances with ``is_stub=True``.
        """
        url = (
            f"{_CANLII_BASE}/caseBrowse/{self._language}/{database_id}/"
            f"?offset={offset}&resultCount={result_count}&api_key={self._api_key}"
        )
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"CanLII caseBrowse failed for {database_id}: {exc}"
            log.warning(msg)
            self.errors.append(msg)
            return []

        raw = response.content
        data: dict[str, Any] = response.json()
        cases = data.get("cases", [])
        results: list[CanLIILawSection] = []
        for case in cases:
            section = self._metadata_to_section(database_id, case)
            section.raw_hash = hashlib.sha256(raw).hexdigest()
            results.append(section)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_case_metadata(
        self,
        database_id: str,
        case_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve case metadata from the CanLII API."""
        url = (
            f"{_CANLII_BASE}/caseCitationBrowse/{self._language}"
            f"/{database_id}/{case_id}/?api_key={self._api_key}"
        )
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPError as exc:
            msg = f"CanLII metadata fetch failed for {database_id}/{case_id}: {exc}"
            log.warning(msg)
            self.errors.append(msg)
            return None

    def _fetch_case_text(
        self,
        database_id: str,
        case_id: str,
    ) -> str:
        """Retrieve the full text HTML of *case_id* from CanLII.

        Returns an empty string if retrieval fails.
        """
        url = (
            f"{_CANLII_BASE}/caseDocumentBrowse/{self._language}"
            f"/{database_id}/{case_id}/index.html?api_key={self._api_key}"
        )
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            log.debug("Full text unavailable for %s/%s: %s", database_id, case_id, exc)
            return ""

    def _metadata_to_section(
        self,
        database_id: str,
        data: dict[str, Any],
    ) -> CanLIILawSection:
        """Convert a raw CanLII metadata dict to a :class:`CanLIILawSection`."""
        jurisdiction = _DB_TO_JURISDICTION.get(database_id, database_id.upper())

        # Decision date comes back as "YYYY-MM-DD" or "YYYY-MM" or "YYYY"
        decision_date: date | None = None
        raw_date = data.get("decisionDate") or data.get("date") or ""
        if raw_date:
            try:
                parts = raw_date.split("-")
                if len(parts) == 3:
                    decision_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                elif len(parts) >= 1:
                    decision_date = date(int(parts[0]), 1, 1)
            except (ValueError, IndexError):
                pass

        style_of_cause = data.get("title", data.get("style", ""))
        citation = data.get("citation", data.get("caseId", {}).get("id", ""))
        case_id_str = (
            (data.get("caseId") or {}).get("id", "")
            if isinstance(data.get("caseId"), dict)
            else str(data.get("caseId", ""))
        )

        source_url = (
            data.get("url")
            or f"https://www.canlii.org/{self._language}/{database_id}/doc/{case_id_str}/"
        )

        return CanLIILawSection(
            jurisdiction=jurisdiction,
            source="CanLII",
            law_title=style_of_cause,
            law_type="decision",
            chapter=citation,
            section_number="",
            section_heading=style_of_cause,
            section_text="",
            language=self._language,
            source_url=source_url,
            consolidation_date=decision_date,
            raw_hash="",
            is_stub=True,
        )
