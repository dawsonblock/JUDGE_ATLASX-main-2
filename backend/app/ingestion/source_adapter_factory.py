"""Factory for instantiating Canadian source adapters.

Centralises the adapter-construction logic so that:
* API keys (CanLII, Lexum) are injected from ``Settings`` rather than
  scattered across caller sites.
* The ``public_record_authority`` field is always wired from the DB row.
* Callers obtain a ``CanadianSourceAdapter`` without knowing each adapter's
  exact constructor signature.

Usage::

    from app.ingestion.source_adapter_factory import build_adapter
    from app.core.config import get_settings

    adapter = build_adapter(source, get_settings())
    if adapter is None:
        # parser key unknown — no adapter registered
        ...
    result = adapter.run()
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

from app.ingestion.adapters import CanadianSourceAdapter
from app.ingestion.source_adapters import ADAPTER_REGISTRY

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.models.entities import SourceRegistry

logger = logging.getLogger(__name__)

_LAWS_XML_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")

_PARSER_SECRET_NAMES: dict[str, str] = {
    "canlii_api": "JTA_CANLII_API_KEY",
    "scc_lexum_api": "LEXUM_API_KEY",
}


def parse_laws_xml_target_ids(raw_value: str | None) -> list[str]:
    """Parse and validate configured Justice Canada law target IDs.

    Accepts a comma-separated string (for env var compatibility) and returns
    a normalized list. IDs must be non-empty and match ``[A-Za-z0-9-]+``.
    """
    if raw_value is None:
        return ["C-46"]

    candidates = [segment.strip() for segment in raw_value.split(",")]
    target_ids = [value for value in candidates if value]
    if not target_ids:
        raise ValueError("JTA_LAWS_XML_TARGET_IDS must include at least one target ID")

    invalid = [value for value in target_ids if _LAWS_XML_TARGET_ID_RE.fullmatch(value) is None]
    if invalid:
        raise ValueError(
            "Malformed law target IDs in JTA_LAWS_XML_TARGET_IDS: "
            + ", ".join(invalid)
        )

    return target_ids


def required_secret_name_for_parser(parser_key: str | None) -> str | None:
    """Return the env var name required for *parser_key*, if any."""
    if not parser_key:
        return None
    return _PARSER_SECRET_NAMES.get(parser_key)


def resolve_api_key_for_parser(parser_key: str | None, settings: "Settings") -> str | None:
    """Resolve a parser-specific API key without cross-wiring credentials."""
    if parser_key == "canlii_api":
        return getattr(settings, "canlii_api_key", None)
    if parser_key == "scc_lexum_api":
        return getattr(settings, "lexum_api_key", None) or os.environ.get("LEXUM_API_KEY")
    return None


def missing_required_secret_for_parser(
    parser_key: str | None,
    settings: "Settings",
) -> str | None:
    """Return the required secret name when a runnable parser is missing it."""
    secret_name = required_secret_name_for_parser(parser_key)
    if secret_name is None:
        return None
    if resolve_api_key_for_parser(parser_key, settings):
        return None
    return secret_name


def build_adapter(
    source: "SourceRegistry",
    settings: "Settings",
) -> CanadianSourceAdapter | None:
    """Return a configured :class:`CanadianSourceAdapter` for *source*.

    Returns ``None`` if no adapter is registered for ``source.parser``.

    The factory will:

    1. Look up the adapter class in ``ADAPTER_REGISTRY``.
     2. Inject the parser-specific ``api_key`` without cross-wiring CanLII and
         Lexum credentials.
    3. Pass ``public_record_authority`` from the DB row.
    """
    parser_key = source.parser
    if not parser_key:
        logger.warning(
            "Source %r has no parser key; skipping factory.", source.source_key
        )
        return None

    adapter_cls = ADAPTER_REGISTRY.get(parser_key)
    if adapter_cls is None:
        logger.warning(
            "No adapter registered for parser %r (source %r).",
            parser_key,
            source.source_key,
        )
        return None

    common_kwargs: dict = {
        "source_key": source.source_key,
        "base_url": source.base_url or "",
        "allowed_domains_json": source.allowed_domains or "[]",
        "public_record_authority": source.public_record_authority,
    }

    api_key = resolve_api_key_for_parser(parser_key, settings)
    if api_key:
        common_kwargs["api_key"] = api_key

    # Parse config_json once and forward adapter-specific fields.
    config: dict = {}
    if source.config_json:
        try:
            config = json.loads(source.config_json)
        except json.JSONDecodeError:
            logger.warning(
                "Source %r has malformed config_json; ignoring extra config.",
                source.source_key,
            )

    if parser_key == "ckan_api":
        resource_id = config.get("resource_id")
        if resource_id:
            common_kwargs["resource_id"] = resource_id
        page_limit = config.get("page_limit")
        if page_limit is not None:
            common_kwargs["page_limit"] = int(page_limit)
        max_pages = config.get("max_pages")
        if max_pages is not None:
            common_kwargs["max_pages"] = int(max_pages)
        offset = config.get("offset")
        if offset is not None:
            common_kwargs["offset"] = int(offset)

    if parser_key == "canlii_api":
        databases = config.get("databases")
        if databases:
            common_kwargs["databases"] = databases
        result_count = config.get("result_count")
        if result_count:
            common_kwargs["result_count"] = int(result_count)
        offset = config.get("offset")
        if offset is not None:
            common_kwargs["offset"] = int(offset)

    if parser_key == "federal_court_html":
        year = config.get("year")
        if year:
            common_kwargs["year"] = int(year)
        limit = config.get("limit")
        if limit:
            common_kwargs["limit"] = int(limit)

    if parser_key == "laws_justice_xml":
        try:
            common_kwargs["target_unique_ids"] = parse_laws_xml_target_ids(
                getattr(settings, "laws_xml_target_ids", None)
            )
        except ValueError as exc:
            logger.error(
                "Invalid laws XML target IDs for source %r: %s",
                source.source_key,
                exc,
            )
            return None

    source_class = getattr(source, "source_class", None)
    if source_class != "machine_ingest":
        raise ValueError(
            f"Source '{source.source_key}' has source_class={source_class!r} which "
            f"cannot be auto-ingested. Only 'machine_ingest' sources may be run. "
            f"Classify this source correctly before enabling adapter runs."
        )

    try:
        adapter: CanadianSourceAdapter = adapter_cls(**common_kwargs)
    except TypeError as exc:
        logger.error(
            "Failed to instantiate adapter %r for source %r: %s",
            adapter_cls.__name__,
            source.source_key,
            exc,
        )
        return None

    return adapter
