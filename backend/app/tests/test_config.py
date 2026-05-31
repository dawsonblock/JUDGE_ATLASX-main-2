"""Tests for app.core.config.Settings.

Verifies default values and environment variable handling for the Pydantic
Settings v2 config class.
"""

from __future__ import annotations

import os

import pytest


def test_dev_minimal_load():
    """Settings loads successfully with only JTA_APP_ENV=development set."""
    # conftest.py already sets this, but be explicit.
    from app.core.config import Settings  # noqa: PLC0415

    s = Settings(_env_file=None)
    assert s.app_env == "development"


def test_dev_ignores_missing_redis(monkeypatch):
    """In development mode, redis_url is not required and defaults to None."""
    monkeypatch.delenv("JTA_REDIS_URL", raising=False)
    from app.core.config import Settings  # noqa: PLC0415

    s = Settings(_env_file=None)
    assert s.redis_url is None


def test_jwt_secret_default():
    """jwt_secret_key has a placeholder default (not empty)."""
    from app.core.config import Settings  # noqa: PLC0415

    s = Settings(_env_file=None)
    assert s.jwt_secret_key, "jwt_secret_key must not be empty"
    assert len(s.jwt_secret_key) >= 10, "jwt_secret_key default should be non-trivial"


def test_get_settings_is_cached():
    """get_settings() returns the same object on repeated calls (lru_cache)."""
    from app.core.config import get_settings  # noqa: PLC0415

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2, "get_settings() should return a cached singleton"
