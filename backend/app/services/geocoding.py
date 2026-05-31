"""Geocoding service with caching and hardening.

This module provides geocoding functionality with:
- Caching to avoid redundant API calls
- Status tracking (exact, approximate, ambiguous, failed, manual_required)
- Confidence scoring
- Provider/source tracking
- Rules to prevent silent guessing and block ambiguous results from public publishing
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.models.geocode_cache import GeocodeCache

logger = logging.getLogger(__name__)

# Geocoding status constants
STATUS_EXACT = "exact"
STATUS_APPROXIMATE = "approximate"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_FAILED = "failed"
STATUS_MANUAL_REQUIRED = "manual_required"

# Confidence thresholds
CONFIDENCE_THRESHOLD_EXACT = 0.95
CONFIDENCE_THRESHOLD_APPROXIMATE = 0.70
CONFIDENCE_THRESHOLD_AMBIGUOUS = 0.40


class GeocodingService:
    """Service for geocoding location queries with caching and hardening."""

    def __init__(self, db: Session):
        self.db = db

    def _hash_query(self, query: str) -> str:
        """Generate a hash for the query string."""
        return hashlib.sha256(query.lower().encode()).hexdigest()

    def geocode(
        self,
        query: str,
        provider: str = "nominatim",
        source_key: str | None = None,
        country: str | None = None,
        province: str | None = None,
    ) -> GeocodeCache:
        """Geocode a location query with caching.

        Args:
            query: The location query string
            provider: The geocoding provider to use
            source_key: The source key that triggered this lookup
            country: Expected country code (e.g., "CA")
            province: Expected province/state

        Returns:
            GeocodeCache with the result
        """
        query_hash = self._hash_query(query)

        # Check cache first
        cached = (
            self.db.query(GeocodeCache)
            .filter(GeocodeCache.query_hash == query_hash)
            .first()
        )
        if cached:
            cached.last_used_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.debug(f"Geocode cache hit for query: {query}")
            return cached

        # Perform geocoding
        result = self._geocode_external(query, provider, country, province)

        # Store in cache
        geocode_cache = GeocodeCache(
            query=query,
            query_hash=query_hash,
            latitude=result.get("lat"),
            longitude=result.get("lng"),
            location_name=result.get("location_name"),
            formatted_address=result.get("formatted_address"),
            status=result.get("status", STATUS_FAILED),
            confidence=result.get("confidence", 0.0),
            provider=provider,
            country=result.get("country", country),
            province=result.get("province", province),
            jurisdiction=result.get("jurisdiction"),
            source_key=source_key,
            metadata_json=json.dumps(result.get("metadata", {})),
            last_used_at=datetime.now(timezone.utc),
        )

        self.db.add(geocode_cache)
        self.db.commit()

        logger.info(f"Geocoded query: {query} -> {result.get('status')}")
        return geocode_cache

    def _geocode_external(
        self,
        query: str,
        provider: str,
        country: str | None,
        province: str | None,
    ) -> dict[str, Any]:
        """Perform external geocoding lookup.

        Args:
            query: The location query
            provider: The geocoding provider
            country: Expected country code
            province: Expected province

        Returns:
            Dict with lat, lng, status, confidence, etc.
        """
        if provider == "nominatim":
            return self._geocode_nominatim(query, country, province)
        else:
            logger.warning(f"Unknown geocoding provider: {provider}")
            return {"status": STATUS_FAILED, "confidence": 0.0}

    def _geocode_nominatim(
        self,
        query: str,
        country: str | None,
        province: str | None,
    ) -> dict[str, Any]:
        """Geocode using OpenStreetMap Nominatim.

        Args:
            query: The location query
            country: Expected country code (e.g., "CA")
            province: Expected province

        Returns:
            Dict with lat, lng, status, confidence, etc.
        """
        try:
            # Build query with country/province filters
            search_query = query
            if province:
                search_query = f"{search_query}, {province}"
            if country:
                search_query = f"{search_query}, {country}"

            encoded_query = quote(search_query)
            url = f"https://nominatim.openstreetmap.org/search?q={encoded_query}&format=json&limit=5"

            with httpx.Client(timeout=10) as client:
                response = client.get(url)
                response.raise_for_status()
                results = response.json()

            if not results:
                return {"status": STATUS_FAILED, "confidence": 0.0}

            if len(results) == 1:
                # Single result - likely exact
                result = results[0]
                return {
                    "lat": float(result["lat"]),
                    "lng": float(result["lon"]),
                    "location_name": result.get("display_name"),
                    "formatted_address": result.get("display_name"),
                    "status": STATUS_EXACT,
                    "confidence": CONFIDENCE_THRESHOLD_EXACT,
                    "country": result.get("country_code"),
                    "province": result.get("state"),
                    "metadata": {"importance": result.get("importance")},
                }
            else:
                # Multiple results - check if top result is significantly better
                top_result = results[0]
                second_result = results[1]
                importance_diff = top_result.get("importance", 0) - second_result.get("importance", 0)

                if importance_diff > 0.3:
                    # Top result is significantly better - treat as approximate
                    return {
                        "lat": float(top_result["lat"]),
                        "lng": float(top_result["lon"]),
                        "location_name": top_result.get("display_name"),
                        "formatted_address": top_result.get("display_name"),
                        "status": STATUS_APPROXIMATE,
                        "confidence": CONFIDENCE_THRESHOLD_APPROXIMATE,
                        "country": top_result.get("country_code"),
                        "province": top_result.get("state"),
                        "metadata": {
                            "importance": top_result.get("importance"),
                            "result_count": len(results),
                        },
                    }
                else:
                    # Results are similar - ambiguous
                    return {
                        "lat": float(top_result["lat"]),
                        "lng": float(top_result["lon"]),
                        "location_name": top_result.get("display_name"),
                        "formatted_address": top_result.get("display_name"),
                        "status": STATUS_AMBIGUOUS,
                        "confidence": CONFIDENCE_THRESHOLD_AMBIGUOUS,
                        "country": top_result.get("country_code"),
                        "province": top_result.get("state"),
                        "metadata": {
                            "importance": top_result.get("importance"),
                            "result_count": len(results),
                            "alternatives": results[:3],
                        },
                    }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during geocoding: {e}")
            return {"status": STATUS_FAILED, "confidence": 0.0}
        except Exception as e:
            logger.error(f"Error during geocoding: {e}", exc_info=True)
            return {"status": STATUS_FAILED, "confidence": 0.0}

    def is_safe_for_public(self, geocode_cache: GeocodeCache) -> bool:
        """Check if a geocode result is safe for public publishing.

        Rules:
        - Block public publishing if status is ambiguous
        - Block public publishing if status is failed
        - Block public publishing if status is manual_required
        - Allow exact and approximate results

        Args:
            geocode_cache: The geocode cache entry

        Returns:
            True if safe for public publishing, False otherwise
        """
        return geocode_cache.status in (STATUS_EXACT, STATUS_APPROXIMATE)

    def get_by_query(self, query: str) -> GeocodeCache | None:
        """Get cached geocode result by query string.

        Args:
            query: The location query string

        Returns:
            GeocodeCache if found, None otherwise
        """
        query_hash = self._hash_query(query)
        return (
            self.db.query(GeocodeCache)
            .filter(GeocodeCache.query_hash == query_hash)
            .first()
        )
