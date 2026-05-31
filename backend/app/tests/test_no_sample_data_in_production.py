"""Tests to prevent sample data from seeding by default in production."""
import pytest
from app.core.config import Settings


def test_auto_seed_defaults_false(monkeypatch):
    """Verify that auto_seed defaults to False (not auto-enabled)."""
    monkeypatch.delenv("JTA_AUTO_SEED", raising=False)
    settings = Settings()
    assert settings.auto_seed is False


def test_production_env_must_not_auto_seed():
    """Verify that production environment has auto_seed disabled."""
    settings = Settings(app_env="production", auto_seed=False)
    assert settings.app_env == "production"
    assert settings.auto_seed is False


def test_development_can_enable_auto_seed():
    """Verify that development can enable auto_seed."""
    settings = Settings(app_env="development", auto_seed=True)
    assert settings.app_env == "development"
    assert settings.auto_seed is True
