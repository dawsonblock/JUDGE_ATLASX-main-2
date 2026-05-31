"""Tests for backend app import and route registration.

Verifies that app.main imports cleanly in development mode and
that all route groups are registered.
"""

from __future__ import annotations

import pytest


def test_app_import_succeeds():
    """app.main can be imported without raising."""
    from app.main import app  # noqa: PLC0415

    assert app is not None, "app should not be None after import"


def test_app_has_routes():
    """The FastAPI app must have at least one route registered."""
    from app.main import app  # noqa: PLC0415

    assert len(app.routes) > 0, "No routes registered on the FastAPI app"


def test_app_docs_route_present():
    """The /docs route should be available (openapi_url is set)."""
    from app.main import app  # noqa: PLC0415

    assert app.openapi_url is not None, "openapi_url should not be None in non-prod"
