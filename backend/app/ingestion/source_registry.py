"""Compatibility source registry accessor used by legacy tests.

Primary source-of-truth remains database SourceRegistry rows and the
proof-generated source registry status artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path


def get_source_registry() -> dict[str, dict]:
    """Return a source registry mapping for test-time consistency checks.

    Falls back to an empty mapping when proof artifacts are unavailable.
    """
    repo_root = Path(__file__).resolve().parents[3]
    status_path = (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "source_registry_status.json"
    )
    if not status_path.exists():
        return {}

    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    rows = payload.get("sources")
    if not isinstance(rows, list):
        return {}

    registry: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_key = row.get("source_key")
        if not source_key:
            continue
        lifecycle_state = row.get("lifecycle_state") or "broken"
        automation_status = row.get("automation_status")
        is_active = bool(row.get("is_active", False))
        registry[str(source_key)] = {
            "source_key": source_key,
            "lifecycle_state": lifecycle_state,
            "is_runnable": lifecycle_state in {"runnable", "enabled_runnable"},
            "is_active": is_active,
            "automation_status": automation_status,
        }

    return registry
