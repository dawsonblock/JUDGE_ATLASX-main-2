"""Tests for run_web_monitor script's sync wrapper.

Verifies that:
- run_web_monitor_target_sync is a regular (non-async) callable
- It is exported from the app.ingestion.web_monitor package __all__
"""
from __future__ import annotations

import inspect


def test_run_web_monitor_target_sync_is_not_coroutine() -> None:
    """run_web_monitor_target_sync must be synchronous so the CLI can call it directly."""
    from app.ingestion.web_monitor import run_web_monitor_target_sync

    assert callable(run_web_monitor_target_sync)
    assert not inspect.iscoroutinefunction(run_web_monitor_target_sync), (
        "run_web_monitor_target_sync must be a plain sync function, not async"
    )


def test_run_web_monitor_target_sync_in_package_all() -> None:
    """run_web_monitor_target_sync must be listed in the package __all__."""
    import app.ingestion.web_monitor as wm_pkg

    assert hasattr(wm_pkg, "__all__"), "web_monitor package should define __all__"
    assert "run_web_monitor_target_sync" in wm_pkg.__all__
