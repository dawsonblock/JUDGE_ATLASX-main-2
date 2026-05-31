"""Ingestion queue factory with backend selection.

This module provides a factory for creating ingestion queue backends
based on configuration. Supports in-process (alpha-only) and Postgres
(alpha-durable, non-production-qualified) backends.

Usage::

    from app.workers.ingestion_queue import get_ingestion_queue

    queue = get_ingestion_queue()
    job_id = queue.enqueue("federal_court_canada")
    status = queue.get_status(job_id)
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

from app.core.config import get_settings
from app.workers.inprocess_queue import InProcessIngestionQueue
from app.workers.postgres_queue import PostgresIngestionQueue
from app.workers.queue_backend import IngestionQueueBackend

logger = __import__("logging").getLogger(__name__)

# Module-level singleton queue
_QUEUE: IngestionQueueBackend | None = None
_QUEUE_LOCK = threading.Lock()


def _reset_ingestion_queue_for_tests() -> None:
    """Clear the singleton queue for test isolation.

    This function should only be called from test code to ensure
    test isolation when testing queue behavior.
    """
    global _QUEUE
    with _QUEUE_LOCK:
        _QUEUE = None


def get_ingestion_queue(settings: SimpleNamespace | None = None) -> IngestionQueueBackend:
    """Return the process-wide ingestion queue singleton.

    The backend is selected based on the ``ingestion_queue_backend``
    configuration setting:
    - "inprocess": InProcessIngestionQueue (alpha-only, not production-capable)
        - "postgres": PostgresIngestionQueue
            (implemented alpha-durable backend, not production-qualified)

    Args:
        settings: Optional settings object. If not provided, uses
            get_settings() to load configuration.

    Returns:
        The configured ingestion queue backend instance.

    Raises:
        ValueError: If an unsupported backend is configured.
    """
    global _QUEUE
    if _QUEUE is None:
        with _QUEUE_LOCK:
            if _QUEUE is None:
                if settings is None:
                    settings = get_settings()
                backend = settings.ingestion_queue_backend

                if backend == "inprocess":
                    _QUEUE = InProcessIngestionQueue()
                    logger.info("Initialized in-process ingestion queue (alpha-only)")
                elif backend == "postgres":
                    _QUEUE = PostgresIngestionQueue()
                    logger.info(
                        "Initialized Postgres ingestion queue "
                        "(alpha-durable, not production-qualified)"
                    )
                else:
                    raise ValueError(
                        f"Unsupported ingestion queue backend: {backend}. "
                        f"Supported backends: inprocess, postgres"
                    )
    return _QUEUE
