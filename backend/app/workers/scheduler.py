"""In-process APScheduler for web-monitor ingestion jobs.

Builds one ``IntervalTrigger`` job per active, non-manual SourceRegistry row
that has a matching ``WebMonitorTarget``.  The scheduler is started inside the
FastAPI ``lifespan`` context and shut down gracefully on application exit.
"""

from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.ingestion.web_monitor.crawlee_runner import run_web_monitor_target
from app.ingestion.web_monitor.source_targets import EXAMPLE_TARGETS
from app.models.entities import SourceRegistry

log = logging.getLogger(__name__)

# Build source_key → WebMonitorTarget lookup once at import time.
_TARGET_BY_SOURCE_KEY: dict = {
    target.source_key: target for target in EXAMPLE_TARGETS.values()
}


async def _run_source_job(
    source_key: str,
    db_factory: Callable[[], Session],
) -> None:
    """Execute a single scheduled web-monitor ingestion run.

    Errors are caught and logged so that one failing source does not kill
    the scheduler event loop.
    """
    target = _TARGET_BY_SOURCE_KEY.get(source_key)
    if target is None:
        log.warning(
            "Scheduled job: no WebMonitorTarget registered for source_key=%s; skipping",
            source_key,
        )
        return

    with db_factory() as db:
        try:
            run = await run_web_monitor_target(target, db)
            log.info(
                "Scheduled run complete: source_key=%s fetched=%s persisted=%s errors=%s",
                source_key,
                run.fetched_count,
                run.persisted_count,
                run.error_count,
            )
        except Exception:
            log.exception(
                "Scheduled run failed: source_key=%s",
                source_key,
            )


def build_scheduler(db_factory: Callable[[], Session]) -> AsyncIOScheduler:
    """Build an ``AsyncIOScheduler`` with one job per schedulable source.

    A source is schedulable when:
    - ``SourceRegistry.is_active`` is ``True``
    - ``SourceRegistry.fetch_method`` is not ``"manual"``
    - A ``WebMonitorTarget`` in ``EXAMPLE_TARGETS`` matches its ``source_key``

    Job interval is taken from ``WebMonitorTarget.crawl_interval_hours``.

    Args:
        db_factory: Callable that returns a SQLAlchemy session (context manager).

    Returns:
        Configured ``AsyncIOScheduler`` (not yet started).
    """
    scheduler = AsyncIOScheduler()

    try:
        with db_factory() as db:
            active_rows: list[SourceRegistry] = (
                db.query(SourceRegistry)
                .filter(
                    SourceRegistry.is_active.is_(True),
                    SourceRegistry.fetch_method != "manual",
                )
                .all()
            )
    except Exception:
        log.exception(
            "build_scheduler: could not query SourceRegistry; "
            "no jobs will be scheduled"
        )
        return scheduler

    for row in active_rows:
        target = _TARGET_BY_SOURCE_KEY.get(row.source_key)
        if target is None:
            log.debug(
                "build_scheduler: skipping source_key=%s — no matching WebMonitorTarget",
                row.source_key,
            )
            continue

        interval_hours = target.crawl_interval_hours
        scheduler.add_job(
            _run_source_job,
            trigger=IntervalTrigger(hours=interval_hours),
            args=[row.source_key, db_factory],
            id=f"web_monitor_{row.source_key}",
            name=f"Web monitor: {row.source_name}",
            replace_existing=True,
        )
        log.info(
            "build_scheduler: scheduled source_key=%s every %sh",
            row.source_key,
            interval_hours,
        )

    return scheduler
