from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.main import _validate_production_safety
from app.workers.ingestion_queue import (
    _reset_ingestion_queue_for_tests,
    get_ingestion_queue,
)
from app.workers.inprocess_queue import InProcessIngestionQueue
from app.workers.postgres_queue import PostgresIngestionQueue


def test_get_ingestion_queue_uses_inprocess_backend() -> None:
    _reset_ingestion_queue_for_tests()
    queue = get_ingestion_queue(
        settings=SimpleNamespace(ingestion_queue_backend="inprocess")
    )
    assert queue is not None
    assert isinstance(queue, InProcessIngestionQueue)
    assert queue._capabilities.supports_production is False
    assert queue._capabilities.implementation_status == "alpha"


def test_get_ingestion_queue_uses_postgres_backend() -> None:
    _reset_ingestion_queue_for_tests()
    queue = get_ingestion_queue(settings=SimpleNamespace(ingestion_queue_backend="postgres"))
    assert queue is not None
    assert isinstance(queue, PostgresIngestionQueue)
    assert queue._capabilities.supports_production is False
    assert queue._capabilities.implementation_status == "alpha"


def test_get_ingestion_queue_rejects_invalid_backend() -> None:
    _reset_ingestion_queue_for_tests()
    with pytest.raises(ValueError, match="Unsupported ingestion queue backend"):
        get_ingestion_queue(settings=SimpleNamespace(ingestion_queue_backend="invalid"))


def test_production_rejects_inprocess_ingestion_queue_backend() -> None:
    settings = SimpleNamespace(
        app_env="production",
        jwt_secret_key="this-is-a-strong-production-secret-that-is-long-enough",
        first_admin_secret=None,
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        admin_token=None,
        admin_review_token=None,
        ingestion_queue_backend="inprocess",
        rate_limit_backend="redis",
        redis_url="redis://localhost:6379/0",
        evidence_store_required=True,
    )

    with pytest.raises(SystemExit) as exc_info:
        _validate_production_safety(settings)

    assert exc_info.value.code == 1


def test_non_production_allows_inprocess_ingestion_queue_backend() -> None:
    settings = SimpleNamespace(
        app_env="development",
        jwt_secret_key="CHANGE-ME-BEFORE-PRODUCTION",
        first_admin_secret=None,
        jwt_auth_enabled=False,
        enable_legacy_admin_token=True,
        admin_token="local-dev-token",
        admin_review_token="local-review-token",
        ingestion_queue_backend="inprocess",
        rate_limit_backend="memory",
        redis_url=None,
        evidence_store_required=False,
    )

    _validate_production_safety(settings)
