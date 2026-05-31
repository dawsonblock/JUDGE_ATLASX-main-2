"""Canonical source status derivation for SourceRegistry visibility APIs."""

from __future__ import annotations

from enum import StrEnum

from app.ingestion.automation_statuses import (
    ADAPTER_MISSING,
    DEPRECATED,
    DISABLED_STUB,
    LIFECYCLE_ADAPTER_MISSING,
    LIFECYCLE_BLOCKED_SECRET,
    LIFECYCLE_DEPRECATED,
    LIFECYCLE_DISABLED_STUB,
    LIFECYCLE_MANUAL_REFERENCE,
    LIFECYCLE_PORTAL_REFERENCE,
    LIFECYCLE_RUNNABLE,
    LIFECYCLE_RUNNABLE_DISABLED,
    MACHINE_READY_DISABLED,
    MACHINE_READY_ENABLED,
    MANUAL_ONLY,
    PORTAL_ONLY,
)


class SourceStatus(StrEnum):
    RUNNABLE = "runnable"
    RUNNABLE_DISABLED = "runnable_disabled"
    PORTAL_REFERENCE = "portal_reference"
    MANUAL_REFERENCE = "manual_reference"
    ADAPTER_MISSING = "adapter_missing"
    BLOCKED_SECRET = "blocked_secret"
    DISABLED_STUB = "disabled_stub"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


_LIFECYCLE_MAP: dict[str, SourceStatus] = {
    LIFECYCLE_RUNNABLE: SourceStatus.RUNNABLE,
    LIFECYCLE_RUNNABLE_DISABLED: SourceStatus.RUNNABLE_DISABLED,
    LIFECYCLE_PORTAL_REFERENCE: SourceStatus.PORTAL_REFERENCE,
    LIFECYCLE_MANUAL_REFERENCE: SourceStatus.MANUAL_REFERENCE,
    LIFECYCLE_ADAPTER_MISSING: SourceStatus.ADAPTER_MISSING,
    LIFECYCLE_BLOCKED_SECRET: SourceStatus.BLOCKED_SECRET,
    LIFECYCLE_DISABLED_STUB: SourceStatus.DISABLED_STUB,
    LIFECYCLE_DEPRECATED: SourceStatus.DEPRECATED,
}

_AUTOMATION_MAP: dict[str, SourceStatus] = {
    MACHINE_READY_ENABLED: SourceStatus.RUNNABLE,
    MACHINE_READY_DISABLED: SourceStatus.RUNNABLE_DISABLED,
    PORTAL_ONLY: SourceStatus.PORTAL_REFERENCE,
    MANUAL_ONLY: SourceStatus.MANUAL_REFERENCE,
    ADAPTER_MISSING: SourceStatus.ADAPTER_MISSING,
    "blocked_secret": SourceStatus.BLOCKED_SECRET,
    DISABLED_STUB: SourceStatus.DISABLED_STUB,
    DEPRECATED: SourceStatus.DEPRECATED,
}

_SOURCE_CLASS_MAP: dict[str, SourceStatus] = {
    "portal_reference": SourceStatus.PORTAL_REFERENCE,
    "manual_reference": SourceStatus.MANUAL_REFERENCE,
    "disabled_stub": SourceStatus.DISABLED_STUB,
}


def derive_source_status(
    *,
    explicit_status: str | None,
    lifecycle_state: str | None,
    automation_status: str | None,
    source_class: str | None,
) -> SourceStatus:
    """Return canonical SourceStatus from the richest available source signals."""
    if explicit_status:
        try:
            status = SourceStatus(explicit_status)
            if status != SourceStatus.UNKNOWN:
                return status
        except ValueError:
            pass

    if lifecycle_state and lifecycle_state in _LIFECYCLE_MAP:
        return _LIFECYCLE_MAP[lifecycle_state]

    if automation_status and automation_status in _AUTOMATION_MAP:
        return _AUTOMATION_MAP[automation_status]

    if source_class and source_class in _SOURCE_CLASS_MAP:
        return _SOURCE_CLASS_MAP[source_class]

    return SourceStatus.UNKNOWN
