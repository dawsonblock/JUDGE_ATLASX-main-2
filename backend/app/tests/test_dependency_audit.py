"""Dependency audit test — imports all runtime packages used by backend modules.

Ensures that:
1. All declared runtime dependencies can be imported
2. No missing dependency errors in a clean environment

This test runs in the test suite so that CI catches missing dependencies early.
"""

from __future__ import annotations

import importlib

import pytest


# ---------------------------------------------------------------------------
# Runtime packages declared in pyproject.toml [project.dependencies]
# ---------------------------------------------------------------------------

RUNTIME_PACKAGES = [
    # Package name → importable module name
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("sqlalchemy", "sqlalchemy"),
    ("alembic", "alembic"),
    ("psycopg", "psycopg"),
    ("pydantic-settings", "pydantic_settings"),
    ("httpx", "httpx"),
    ("lxml", "lxml"),
    ("cssselect", "cssselect"),
    ("python-dateutil", "dateutil"),
    ("python-multipart", "multipart"),
    ("geoalchemy2", "geoalchemy2"),
    ("slowapi", "slowapi"),
    ("redis", "redis"),
    ("apscheduler", "apscheduler"),
    ("pypdf", "pypdf"),
    ("python-jose", "jose"),
    ("passlib", "passlib"),
    ("pyyaml", "yaml"),
    ("beautifulsoup4", "bs4"),
    ("email-validator", "email_validator"),
    ("html2text", "html2text"),
    ("click", "click"),
    ("crawlee", "crawlee"),
]


@pytest.mark.parametrize("package_name,module_name", RUNTIME_PACKAGES)
def test_runtime_package_importable(package_name: str, module_name: str) -> None:
    """Each runtime dependency must be importable without errors."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(
            f"Runtime dependency '{package_name}' (import '{module_name}') "
            f"cannot be imported: {exc}\n"
            f"Run: pip install -e '.[test]' to install all dependencies."
        )


# ---------------------------------------------------------------------------
# Core app modules — must import cleanly in isolation
# ---------------------------------------------------------------------------

CORE_APP_MODULES = [
    "app.core.config",
    "app.db.session",
    "app.auth.jwt_handler",
    "app.auth.admin",
    "app.auth.actor",
    "app.models.entities",
    "app.ingestion.adapters",
    "app.ingestion.statuses",
    "app.ingestion.source_rules",
    "app.ingestion.source_registry_ctl",
    "app.ingestion.source_adapter_factory",
    "app.services.snapshot_writer",
    "app.cli.main",
]


@pytest.mark.parametrize("module_name", CORE_APP_MODULES)
def test_core_app_module_importable(module_name: str) -> None:
    """Core app modules must import cleanly (no missing deps, no syntax errors)."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(
            f"Core module '{module_name}' cannot be imported: {exc}\n"
            f"This indicates a missing dependency or broken import chain."
        )
