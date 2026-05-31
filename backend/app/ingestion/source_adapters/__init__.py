"""Source-specific ingestion adapters for the Canada / Saskatchewan pipeline.

Each module in this package implements one parser/fetcher pair identified by
the ``parser`` field in ``SourceRegistry`` / the YAML config.

Adapter registry (``ADAPTER_REGISTRY``) maps the ``parser`` key from
``SourceRegistry.parser`` to a callable that returns a configured adapter
instance.  All adapters must subclass :class:`app.ingestion.adapters.SourceAdapter`
and produce only record types that the source's safety rules permit
(validated by :mod:`app.ingestion.source_rules`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter
from app.ingestion.source_adapters.ckan_api import CKANApiAdapter
from app.ingestion.source_adapters.crawlee_gov_news import CrawleeGovNewsAdapter
from app.ingestion.source_adapters.crawlee_police_release import (
    CrawleePoliceReleaseAdapter,
)
from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter
from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter
from app.ingestion.source_adapters.laws_justice_xml import LawsJusticeXmlAdapter
from app.ingestion.source_adapters.saskatoon_csv import SaskatoonCsvAdapter
from app.ingestion.source_adapters.saskatoon_police_csv import SaskatoonPoliceCsvAdapter
from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter
from app.ingestion.source_adapters.sk_courts_html import SKCourtsHtmlAdapter
from app.ingestion.source_adapters.sk_legislature_html import SKLegislatureHtmlAdapter
from app.ingestion.source_adapters.statscan_table import StatscanTableAdapter

# Maps SourceRegistry.parser → adapter class
ADAPTER_REGISTRY: dict[str, type] = {
    "saskatoon_csv": SaskatoonCsvAdapter,
    "saskatoon_police_csv": SaskatoonPoliceCsvAdapter,
    "crawlee_police_release": CrawleePoliceReleaseAdapter,
    "sk_courts_html": SKCourtsHtmlAdapter,
    "statscan_table": StatscanTableAdapter,
    "canlii_api": CanLIIApiAdapter,
    "federal_court_html": FederalCourtHtmlAdapter,
    "scc_lexum_api": SCCLexumApiAdapter,
    "crawlee_gov_news": CrawleeGovNewsAdapter,
    "sk_legislature_html": SKLegislatureHtmlAdapter,
    "laws_justice_html": LawsJusticeHtmlAdapter,
    "laws_justice_xml": LawsJusticeXmlAdapter,
    "ckan_api": CKANApiAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "CanLIIApiAdapter",
    "CKANApiAdapter",
    "CrawleeGovNewsAdapter",
    "CrawleePoliceReleaseAdapter",
    "FederalCourtHtmlAdapter",
    "LawsJusticeHtmlAdapter",
    "LawsJusticeXmlAdapter",
    "SaskatoonCsvAdapter",
    "SaskatoonPoliceCsvAdapter",
    "SCCLexumApiAdapter",
    "SKCourtsHtmlAdapter",
    "SKLegislatureHtmlAdapter",
    "StatscanTableAdapter",
]
