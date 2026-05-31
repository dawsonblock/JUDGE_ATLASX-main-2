"""Legacy admin ingestion router (U.S.-focused, disabled by default).

This module intentionally isolates legacy/U.S.-focused ingestion endpoints from
core Canada-first admin ingestion routes. These routes are only mounted when
JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true.

Legacy endpoints include:
- FBI crime data ingestion
- CourtListener bulk import
- GDELT event ingestion
- Chicago crime data
- Los Angeles crime data
- Other non-Canada experimental feeds

NOTE: These endpoints are intentionally disabled by default as part of the
Canada-first alpha strategy. They are not production-capable and should only be
enabled for development/testing with explicit governance approval.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/admin/ingest", tags=["admin-legacy-ingest"])


def cl_bulk_import(payload: dict, request, db, actor):
    """CourtListener bulk import endpoint (legacy, disabled by default).

    This endpoint is intentionally stubbed out as part of the Canada-first
    strategy. The actual implementation exists in courtlistener_bulk_normalizer.py
    but is not exposed via the API unless explicitly enabled.

    Raises:
        HTTPException: Always raises 404 unless
            JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true
    """
    raise HTTPException(
        status_code=404,
        detail=(
            "Legacy U.S. ingestion routes are disabled. "
            "Enable via JTA_ENABLE_LEGACY_US_INGEST_ROUTES."
        ),
    )


__all__ = ["router", "cl_bulk_import"]
