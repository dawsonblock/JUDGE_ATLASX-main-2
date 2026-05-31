"""GeoNames city coordinate resolver.

Queries the free GeoNames REST API to resolve city names to (lat, lng) pairs.
Requires a free GeoNames account — set JTA_GEONAMES_USERNAME in your .env.

Attribution: GeoNames data is licensed under CC BY 4.0.
See https://www.geonames.org/export/
"""
from __future__ import annotations

# Sentinel: this module is NOT a runtime ingestion source.
# It is a utility-only geocoding helper used in tests and administrative
# tooling.  No source adapter or scheduler calls it at runtime.
# Consumed by check_no_direct_ingestion_network_clients.py and
# check_repo_boundaries.py.
NOT_RUNTIME: bool = True

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

_GEONAMES_API = "https://secure.geonames.org/searchJSON"
_DEFAULT_TIMEOUT = 10


@dataclass
class GeoNamesResult:
    geonames_id: int
    name: str
    latitude: float
    longitude: float
    country_code: str
    admin1_code: str | None


def resolve_city(
    city: str,
    province_state: str | None = None,
    country_code: str | None = None,
    username: str | None = None,
    client: httpx.Client | None = None,
) -> GeoNamesResult | None:
    """Return the best-match GeoNames result for a city name.

    Args:
        city:           City name (e.g. "Toronto").
        province_state: Province or state abbreviation (e.g. "ON", "IL").
        country_code:   ISO-3166 alpha-2 country code (e.g. "CA", "US").
        username:       GeoNames username; falls back to JTA_GEONAMES_USERNAME.
        client:         Optional httpx.Client for testing.

    Returns:
        GeoNamesResult if a match is found, None otherwise.
    """
    effective_username = username or get_settings().geonames_username
    if not effective_username:
        log.debug("GeoNames lookup skipped — no username configured")
        return None

    params: dict[str, str | int] = {
        "q": city,
        "maxRows": 5,
        "featureClass": "P",
        "style": "SHORT",
        "username": effective_username,
    }
    if country_code:
        params["country"] = country_code.upper()
    if province_state:
        params["adminCode1"] = province_state.upper()

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=_DEFAULT_TIMEOUT)

    try:
        response = client.get(_GEONAMES_API, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("GeoNames lookup failed for %r: %s", city, exc)
        return None
    finally:
        if owns_client:
            client.close()

    geonames = data.get("geonames") or []
    if not geonames:
        return None

    best = geonames[0]
    try:
        return GeoNamesResult(
            geonames_id=int(best["geonameId"]),
            name=best.get("name", city),
            latitude=float(best["lat"]),
            longitude=float(best["lng"]),
            country_code=best.get("countryCode", ""),
            admin1_code=best.get("adminCode1"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("GeoNames response parse error for %r: %s", city, exc)
        return None
