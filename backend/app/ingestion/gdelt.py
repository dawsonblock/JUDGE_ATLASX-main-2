# LEGACY: NOT_RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
# This file is quarantined from unconditional runtime loading.
# A reference copy lives in: legacy_disabled/us_ingestion_adapters/gdelt.py
# Do NOT import from app.ingestion.runner without the JTA_GDELT_ENABLED gate.
# ─────────────────────────────────────────────────────────────────────────────

"""GDELT news-link ingester.

Queries the GDELT 2.0 Document API for news articles matching court/judge
keywords in North America and maps results to LegalSource rows
(source_type="news", source_quality="secondary_context").

GDELT records are always TIER_HOLD — they never auto-publish.
Enable with JTA_GDELT_ENABLED=true.

Attribution: The GDELT Project. https://www.gdeltproject.org/
"""

from __future__ import annotations

# ruff: noqa: E402

# Sentinel: experimental / admin-only module.
# The only approved production caller is app.api.routes.admin_ingest,
# gated by JTA_ENABLE_ADMIN_IMPORTS.  This module must not be imported
# by general runtime code or source adapters.
# Consumed by check_no_direct_ingestion_network_clients.py.
NOT_RUNTIME: bool = True

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from app.models.entities import LegalSource
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SOURCE_NAME = "gdelt"

_GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

_DEFAULT_QUERY = (
    "judge OR court OR ruling OR conviction OR sentence "
    "sourcecountry:US OR sourcecountry:CA"
)
_DEFAULT_MODE = "artlist"
_DEFAULT_MAXRECORDS = 25


@dataclass
class GDELTImportResult:
    read_count: int = 0
    persisted_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


def import_gdelt_articles(
    db: Session,
    articles: list[dict],
    commit: bool = True,
) -> GDELTImportResult:
    """Upsert a list of GDELT article dicts as LegalSource rows.

    Expected dict keys per item: ``url``, ``title``, ``domain``,
    ``seendate``, ``language``.
    """
    result = GDELTImportResult()
    now = datetime.now(timezone.utc)

    for idx, article in enumerate(articles, start=1):
        result.read_count += 1
        try:
            url = (article.get("url") or article.get("URL") or "").strip()
            title = (article.get("title") or article.get("TITLE") or "").strip()
            domain = (article.get("domain") or article.get("DOMAIN") or "").strip()
            seen_date_str = (article.get("seendate") or "").strip()

            if not url:
                result.skipped_count += 1
                continue

            existing = db.query(LegalSource).filter_by(url=url).first()
            if existing:
                result.skipped_count += 1
                continue

            url_hash = hashlib.sha256(url.encode()).hexdigest()[:64]
            source_id = f"gdelt-{url_hash[:32]}"
            seen_at = _parse_gdelt_date(seen_date_str) or now
            source = LegalSource(
                source_id=source_id,
                source_type="news",
                source_quality="secondary_context",
                title=title or domain or "GDELT article",
                url=url,
                url_hash=url_hash,
                retrieved_at=now,
                review_status="pending_review",
                public_visibility=False,
                review_notes=f"GDELT import. Domain: {domain}. Seen: {seen_at}.",
            )
            db.add(source)
            db.flush()
            result.persisted_count += 1
        except Exception as exc:  # noqa: BLE001
            result.error_count += 1
            result.errors.append(f"article {idx}: error:{exc}")

    if commit:
        db.commit()
    return result


def fetch_gdelt_articles(
    query: str = _DEFAULT_QUERY,
    maxrecords: int = _DEFAULT_MAXRECORDS,
    client: httpx.Client | None = None,
) -> list[dict] | None:
    """Fetch articles from GDELT Doc API. Returns list of article dicts or None."""
    params = {
        "query": query,
        "mode": _DEFAULT_MODE,
        "maxrecords": maxrecords,
        "format": "json",
    }
    owns = client is None
    if owns:
        client = httpx.Client(timeout=20)
    try:
        resp = client.get(_GDELT_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("articles") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("GDELT fetch error: %s", exc)
        return None
    finally:
        if owns:
            client.close()


def _parse_gdelt_date(value: str) -> datetime | None:
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
