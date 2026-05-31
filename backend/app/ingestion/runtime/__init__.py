"""Ingestion runtime package.

Public surface::

    from app.ingestion.runtime import (
        IngestionRuntime,
        IngestionWorker,
        ReplayResult,
        HealthSnapshot,
        RetryItem,
        CrawlState,
        DedupeResult,
    )
"""

from app.ingestion.runtime.ingestion_runtime import IngestionRuntime
from app.ingestion.runtime.ingestion_worker import IngestionWorker
from app.ingestion.runtime.replay_engine import ReplayResult
from app.ingestion.runtime.source_health import HealthSnapshot
from app.ingestion.runtime.retry_queue import RetryItem
from app.ingestion.runtime.crawl_state import CrawlState
from app.ingestion.runtime.dedupe import DedupeResult, check_parsed_record

__all__ = [
    "IngestionRuntime",
    "IngestionWorker",
    "ReplayResult",
    "HealthSnapshot",
    "RetryItem",
    "CrawlState",
    "DedupeResult",
    "check_parsed_record",
]
