# LEGACY: NOT_RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
# This file is quarantined from unconditional runtime loading.
# A reference copy lives in: legacy_disabled/us_ingestion_adapters/courtlistener.py
# Do NOT import from app.ingestion.runner without the JTA_ENABLE_COURTLISTENER gate.
# ─────────────────────────────────────────────────────────────────────────────

"""CourtListener API adapter.

This adapter uses direct ``httpx`` with Bearer token auth, which is not yet
supported by ``fetch_for_ingestion()``.  Migration to the safe fetcher is
tracked as future work.

.. warning::
   NOT_RUNTIME — callers must set ``JTA_ENABLE_COURTLISTENER=1``.
   The runner (``app.ingestion.runner``) gates its import behind that flag.
"""

from __future__ import annotations

# Sentinel: this adapter is quarantined from unconditional runtime loading.
# Standard ingestion scheduler must NOT import it without the env gate.
# Consumed by check_no_direct_ingestion_network_clients.py.
NOT_RUNTIME: bool = True

import time
from dataclasses import replace
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from app.core.config import Settings, get_settings
from app.ingestion.adapters import ParsedRecord, RawRecord, SourceAdapter


class CourtListenerAdapter(SourceAdapter):
    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.token = (
            token if token is not None else self.settings.courtlistener_api_token
        )
        self.base_url = (base_url or self.settings.courtlistener_base_url).rstrip("/")
        parsed = urlparse(self.base_url)
        self.site_root = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else "https://www.courtlistener.com"
        )
        self.client = client or httpx.Client(
            timeout=self.settings.courtlistener_timeout_seconds
        )
        self.errors: list[str] = []
        self._pages_fetched = 0
        self._dockets_fetched = 0

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.token}"} if self.token else {}

    def fetch(self, since: datetime) -> list[RawRecord]:
        params: dict[str, Any] = {
            "date_modified__gte": since.isoformat(),
            "court__jurisdiction": "FD",
            "order_by": "date_modified,id",
            "fields": "id,resource_uri,docket_number,case_name,court,date_filed,date_terminated,assigned_to_str,date_modified",
        }
        dockets = self._fetch_paginated("/dockets/", params)
        for raw in dockets:
            docket_id = raw.payload.get("id")
            if not docket_id:
                continue
            try:
                raw.payload["docket_entries"] = [
                    entry.payload for entry in self.fetch_docket_entries(docket_id)
                ]
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one docket should not fail the whole run
                self.errors.append(f"docket_entries:{docket_id}:{exc}")
                raw.payload["docket_entries"] = []
            raw.payload["parties"] = [
                party.payload for party in self.fetch_parties(docket_id)
            ]
        return dockets

    def fetch_docket_entries(self, docket_id: str | int) -> list[RawRecord]:
        params = {
            "docket": docket_id,
            "order_by": "recap_sequence_number,entry_number",
            "omit": "recap_documents__plain_text",
        }
        return self._fetch_paginated("/docket-entries/", params)

    def fetch_parties(self, docket_id: str | int) -> list[RawRecord]:
        params = {"docket": docket_id, "filter_nested_results": "true"}
        try:
            return self._fetch_paginated("/parties/", params)
        except httpx.HTTPStatusError as exc:
            self.errors.append(f"parties:{docket_id}:{exc.response.status_code}")
            return []

    def _fetch_paginated(self, path: str, params: dict[str, Any]) -> list[RawRecord]:
        records: list[RawRecord] = []
        next_url: str | None = f"{self.base_url}{path}"
        next_params: dict[str, Any] | None = params
        max_pages = self.settings.courtlistener_max_pages
        pages_fetched = 0
        while next_url and pages_fetched < max_pages:
            try:
                response = self._get_with_retry(
                    next_url, headers=self.headers, params=next_params
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                self.errors.append(f"fetch:{path}:{exc.response.status_code}")
                break
            data = response.json()
            for item in data.get("results", []):
                records.append(RawRecord(source_name="courtlistener", payload=item))
            next_url = data.get("next")
            next_params = None
            pages_fetched += 1
        return records

    def _get_with_retry(
        self, url: str, headers: dict[str, str], params: dict[str, Any] | None = None
    ) -> httpx.Response:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.get(url, headers=headers, params=params)
                if response.status_code == 429 or (500 <= response.status_code < 600):
                    if attempt < max_retries - 1:
                        sleep_seconds = 2**attempt
                        time.sleep(sleep_seconds)
                        continue
                return response
            except httpx.HTTPError:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise
        raise httpx.HTTPError("max retries exceeded")

    def parse(self, raw: RawRecord) -> ParsedRecord:
        """Parse a single docket record (deprecated, use parse_many for entry-level events).

        Extracts document_links from the first recap_document found across all
        docket_entries so that callers relying on the docket-level parse receive
        a populated document_links list.
        """
        base = self._parse_docket_base(raw)
        entries = raw.payload.get("docket_entries") or []
        doc_links: list[str] = []
        for entry in entries:
            for doc in entry.get("recap_documents") or []:
                url = (
                    doc.get("absolute_url")
                    or doc.get("filepath_local")
                    or doc.get("resource_uri")
                )
                if url:
                    doc_links.append(self.absolute_url(str(url)))
        if not doc_links:
            return base
        first_link = doc_links[0]
        return replace(
            base,
            document_links=doc_links,
            source_public_url=first_link,
            source_url=first_link,
        )

    def parse_many(self, raw: RawRecord) -> list[ParsedRecord]:
        """Parse a docket into multiple records, one per docket entry."""
        base = self._parse_docket_base(raw)
        payload = raw.payload
        docket_entries = payload.get("docket_entries", [])
        if not docket_entries:
            return []

        records: list[ParsedRecord] = []
        for entry in docket_entries:
            entry_id = str(entry.get("id")) if entry.get("id") else None
            recap_docs = entry.get("recap_documents") or []
            entry_description = entry.get("description") or ""
            entry_date = _parse_date(
                entry.get("date_entered") or entry.get("date_filed")
            )
            entry_number = entry.get("entry_number")

            for doc in recap_docs:
                doc_id = str(doc.get("id")) if doc.get("id") else None
                doc_url = (
                    doc.get("absolute_url")
                    or doc.get("filepath_local")
                    or doc.get("resource_uri")
                )
                doc_links = [self.absolute_url(str(doc_url))] if doc_url else []
                records.append(
                    ParsedRecord(
                        source_name=base.source_name,
                        docket_id=base.docket_id,
                        docket_number=base.docket_number,
                        court_code=base.court_code,
                        court_name=base.court_name,
                        caption=base.caption,
                        date_filed=base.date_filed,
                        date_terminated=base.date_terminated,
                        judge_name=base.judge_name,
                        docket_text=entry_description,
                        docket_entry_id=entry_id,
                        recap_document_id=doc_id,
                        entry_number=entry_number,
                        entry_date=entry_date,
                        entry_description=entry_description,
                        document_links=doc_links,
                        parties=base.parties,
                        source_url=doc_links[0] if doc_links else base.source_url,
                        source_api_url=doc.get("resource_uri") or base.source_api_url,
                        source_public_url=(
                            doc_links[0] if doc_links else base.source_public_url
                        ),
                        source_quality="court_record",
                        raw={"entry": entry, "docket": payload},
                    )
                )

            if not recap_docs:
                records.append(
                    ParsedRecord(
                        source_name=base.source_name,
                        docket_id=base.docket_id,
                        docket_number=base.docket_number,
                        court_code=base.court_code,
                        court_name=base.court_name,
                        caption=base.caption,
                        date_filed=base.date_filed,
                        date_terminated=base.date_terminated,
                        judge_name=base.judge_name,
                        docket_text=entry_description,
                        docket_entry_id=entry_id,
                        recap_document_id=None,
                        entry_number=entry_number,
                        entry_date=entry_date,
                        entry_description=entry_description,
                        document_links=[],
                        parties=base.parties,
                        source_url=base.source_url,
                        source_api_url=base.source_api_url,
                        source_public_url=base.source_public_url,
                        source_quality="court_record",
                        raw={"entry": entry, "docket": payload},
                    )
                )
        return records

    def _parse_docket_base(self, raw: RawRecord) -> ParsedRecord:
        payload = raw.payload
        source_api_url = (
            self.absolute_url(str(payload.get("resource_uri")))
            if payload.get("resource_uri")
            else None
        )
        source_public_url = _first_present(
            (
                self.absolute_url(str(payload.get("absolute_url")))
                if payload.get("absolute_url")
                else None
            ),
            (
                self.absolute_url(str(payload.get("frontend_url")))
                if payload.get("frontend_url")
                else None
            ),
            (
                self.absolute_url(str(payload.get("docket_absolute_url")))
                if payload.get("docket_absolute_url")
                else None
            ),
            source_api_url,
        )
        return ParsedRecord(
            source_name="courtlistener",
            docket_id=str(payload.get("id")) if payload.get("id") is not None else None,
            docket_number=payload.get("docket_number"),
            court_code=_resource_tail(payload.get("court")),
            court_name=payload.get("court_name") or payload.get("court_str"),
            caption=payload.get("case_name"),
            date_filed=_parse_date(payload.get("date_filed")),
            date_terminated=_parse_date(payload.get("date_terminated")),
            judge_name=payload.get("assigned_to_str"),
            docket_text=payload.get("description"),
            entry_date=_parse_date(payload.get("date_modified")),
            document_links=[],
            parties=payload.get("parties", []),
            source_url=source_public_url,
            source_api_url=source_api_url,
            source_public_url=source_public_url,
            source_quality="court_record",
            raw=payload,
        )

    def absolute_url(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return urljoin(f"{self.site_root}/", value.lstrip("/"))


def _resource_tail(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _first_present(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None
