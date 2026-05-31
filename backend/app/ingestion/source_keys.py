"""Canonical ingestion source key registry.

All code that passes a source key to ``require_source_registry()``,
``_check_source_active()``, or any adapter MUST use the canonical values
defined here.  Legacy aliases accumulated from old routes are mapped to
their canonical equivalents (or to ``None`` for sources that are no longer
supported in this deployment).

Usage::

    from app.ingestion.source_keys import CANONICAL_SOURCE_KEYS, resolve_source_key

    key = resolve_source_key("saskatoon_crime")   # → "saskatoon_open_data_crime"
    key = resolve_source_key("chicago_crime")      # → None  (disabled)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical source keys  (mirrors canada_saskatchewan_sources.yaml)
# ---------------------------------------------------------------------------

SASKATOON_OPEN_DATA_CRIME = "saskatoon_open_data_crime"
SASKATOON_POLICE_OPEN_DATA = "saskatoon_police_open_data"
WEB_MONITOR_SASKATOON_POLICE_NEWS = "web_monitor_saskatoon_police_news"
SK_COURTS_QB_DECISIONS = "sk_courts_qb_decisions"
SK_COURTS_CA_DECISIONS = "sk_courts_ca_decisions"
STATSCAN_CCJS_CRIME_SK = "statscan_ccjs_crime_sk"
STATSCAN_UCR_NATIONAL = "statscan_ucr_national"
CANLII_SK = "canlii_sk"
FEDERAL_COURT_CANADA = "federal_court_canada"
SCC_DECISIONS = "scc_decisions"
SK_JUSTICE_MINISTRY = "sk_justice_ministry"
SK_LEGISLATURE_HANSARD = "sk_legislature_hansard"
CANADA_OPEN_DATA_CRIME = "canada_open_data_crime"
RCMP_SK_NEWS = "rcmp_sk_news"
JUSTICE_CANADA_LAWS_XML = "justice_canada_laws_xml"
# Deprecated name kept as an import-safe alias.
CANADA_JUSTICE_LAWS = JUSTICE_CANADA_LAWS_XML
SASKATOON_OPEN_DATA_PORTAL = "saskatoon_open_data_portal"

# Supplemental keys not in the Saskatchewan YAML but used by active adapters
COURTLISTENER_BULK = "courtlistener_bulk"

CANONICAL_SOURCE_KEYS: frozenset[str] = frozenset(
    [
        SASKATOON_OPEN_DATA_CRIME,
        SASKATOON_POLICE_OPEN_DATA,
        WEB_MONITOR_SASKATOON_POLICE_NEWS,
        SK_COURTS_QB_DECISIONS,
        SK_COURTS_CA_DECISIONS,
        STATSCAN_CCJS_CRIME_SK,
        STATSCAN_UCR_NATIONAL,
        CANLII_SK,
        FEDERAL_COURT_CANADA,
        SCC_DECISIONS,
        SK_JUSTICE_MINISTRY,
        SK_LEGISLATURE_HANSARD,
        CANADA_OPEN_DATA_CRIME,
        RCMP_SK_NEWS,
        JUSTICE_CANADA_LAWS_XML,
        SASKATOON_OPEN_DATA_PORTAL,
        COURTLISTENER_BULK,
    ]
)

# ---------------------------------------------------------------------------
# Legacy alias map
# Keys are old/external strings that may arrive from routes or external callers.
# Values are the canonical key to use, or None if the source is disabled/gone.
# ---------------------------------------------------------------------------

LEGACY_SOURCE_ALIASES: dict[str, str | None] = {
    # Routes in admin_ingest.py that used non-canonical strings
    "saskatoon_crime": SASKATOON_OPEN_DATA_CRIME,
    "statscan": STATSCAN_CCJS_CRIME_SK,
    "gdelt": WEB_MONITOR_SASKATOON_POLICE_NEWS,
    # Out-of-scope sources no longer ingested by this deployment
    "chicago_crime": None,
    "toronto_crime": None,
    "la_crime": None,
    "fbi_crime": None,
    # Normalise any old variations of the statscan key
    "statscan_crime": STATSCAN_CCJS_CRIME_SK,
    "statscan_crime_sk": STATSCAN_CCJS_CRIME_SK,
    # Canonical Justice Canada XML source key migration.
    "canada_justice_laws": JUSTICE_CANADA_LAWS_XML,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_source_key(key: str) -> str | None:
    """Return the canonical source key for *key*.

    Returns:
        The canonical key string if *key* is already canonical or has a known
        alias mapping.  Returns ``None`` if the source is explicitly disabled.
        Returns *key* unchanged if it is already in ``CANONICAL_SOURCE_KEYS``
        (pass-through for callers that already use canonical keys).

    Raises:
        ``KeyError`` is NOT raised for unknown keys; unknown non-canonical keys
        are returned as-is so that callers can handle the validation step
        (e.g. ``require_source_registry`` will raise 404 for unknown sources).
    """
    if key in CANONICAL_SOURCE_KEYS:
        return key
    return LEGACY_SOURCE_ALIASES.get(key, key)


def is_canonical_source_key(key: str) -> bool:
    """Return ``True`` if *key* is a member of ``CANONICAL_SOURCE_KEYS``."""
    return key in CANONICAL_SOURCE_KEYS
