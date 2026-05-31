"""Canonical automation status constants for SourceRegistry.automation_status.

These constants drive two enforcement gates:

1. ``check_ingestion_allowed()`` in source_registry_ctl — rejects ingestion
   unless ``automation_status`` is in ``RUNNABLE_STATUSES``.
2. ``enable_source()`` in admin_sources — rejects enable unless
   ``automation_status`` is in ``ENABLEABLE_STATUSES``, then transitions to
   ``MACHINE_READY_ENABLED`` on success.
3. ``disable_source()`` in admin_sources — transitions
   ``MACHINE_READY_ENABLED → MACHINE_READY_DISABLED`` when disabling.
"""

from __future__ import annotations

from app.workers.queue_backend import JobState

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

MACHINE_READY_DISABLED = "machine_ready_disabled"
MACHINE_READY_ENABLED = "machine_ready_enabled"
ADAPTER_MISSING = "adapter_missing"
PARSER_MISSING = "parser_missing"
NEEDS_ENDPOINT_CONFIGURATION = "needs_endpoint_configuration"
NEEDS_LEGAL_REVIEW = "needs_legal_review"
PORTAL_ONLY = "portal_only"
MANUAL_ONLY = "manual_only"
DISABLED_STUB = "disabled_stub"
QUARANTINED_SOURCE = "quarantined"
DEPRECATED = "deprecated"

# ---------------------------------------------------------------------------
# Gate frozensets
# ---------------------------------------------------------------------------

#: Only a source with this status may transition to enabled via /enable.
ENABLEABLE_STATUSES: frozenset[str] = frozenset({MACHINE_READY_DISABLED})

#: Statuses that permit the scheduler to execute an ingestion run, provided
#: the source also has ``is_active=True``.
RUNNABLE_STATUSES: frozenset[str] = frozenset(
    {
        MACHINE_READY_ENABLED,
    }
)

#: The complete set of recognised automation status values.
ALL_AUTOMATION_STATUSES: frozenset[str] = frozenset(
    {
        MACHINE_READY_DISABLED,
        MACHINE_READY_ENABLED,
        ADAPTER_MISSING,
        PARSER_MISSING,
        NEEDS_ENDPOINT_CONFIGURATION,
        NEEDS_LEGAL_REVIEW,
        PORTAL_ONLY,
        MANUAL_ONLY,
        DISABLED_STUB,
        QUARANTINED_SOURCE,
        DEPRECATED,
    }
)

# ---------------------------------------------------------------------------
# Lifecycle state constants  (SourceRegistry.lifecycle_state)
# ---------------------------------------------------------------------------
# lifecycle_state is a higher-level classification that explains *why* a source
# is in its current state.  It supplements automation_status (which gate-keeps
# runtime behaviour) with human-readable operational context.

LIFECYCLE_RUNNABLE = "runnable"
"""Adapter exists, parser wired, secrets present — ready to run with /enable."""

LIFECYCLE_RUNNABLE_DISABLED = "runnable_disabled"
"""Adapter ready but operator has not yet enabled this source."""

LIFECYCLE_PORTAL_REFERENCE = "portal_reference"
"""Data is only accessible via a human-operated web portal; no fetch API exists."""

LIFECYCLE_ADAPTER_MISSING = "adapter_missing"
"""A machine-ingest source whose adapter/parser has not yet been written."""

LIFECYCLE_BLOCKED_SECRET = "blocked_secret"
"""Adapter exists but requires a secret/credential that is not yet configured."""

LIFECYCLE_DISABLED_STUB = "disabled_stub"
"""Placeholder entry — source is tracked but not yet ready for any use."""

LIFECYCLE_DEPRECATED = "deprecated"
"""This source key is retired.  Use ``canonical_replacement_key`` instead."""

LIFECYCLE_MANUAL_REFERENCE = "manual_reference"
"""Human-curated reference material; not an ingestable data feed."""

#: All recognised lifecycle_state values.
ALL_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {
        LIFECYCLE_RUNNABLE,
        LIFECYCLE_RUNNABLE_DISABLED,
        LIFECYCLE_PORTAL_REFERENCE,
        LIFECYCLE_ADAPTER_MISSING,
        LIFECYCLE_BLOCKED_SECRET,
        LIFECYCLE_DISABLED_STUB,
        LIFECYCLE_DEPRECATED,
        LIFECYCLE_MANUAL_REFERENCE,
    }
)

#: lifecycle_states that must never be run by the scheduler.
NON_RUNNABLE_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {
        LIFECYCLE_PORTAL_REFERENCE,
        LIFECYCLE_ADAPTER_MISSING,
        LIFECYCLE_BLOCKED_SECRET,
        LIFECYCLE_DISABLED_STUB,
        LIFECYCLE_DEPRECATED,
        LIFECYCLE_MANUAL_REFERENCE,
        LIFECYCLE_RUNNABLE_DISABLED,
    }
)

# ---------------------------------------------------------------------------
# Typed block reason codes  (returned by check_ingestion_allowed)
# ---------------------------------------------------------------------------

BLOCK_SOURCE_INACTIVE = "SOURCE_INACTIVE"
BLOCK_NO_AUTOMATION_STATUS = "NO_AUTOMATION_STATUS"
BLOCK_AUTOMATION_STATUS_PREVENTS_RUN = "AUTOMATION_STATUS_PREVENTS_RUN"
BLOCK_SOURCE_DEPRECATED = "SOURCE_DEPRECATED"
BLOCK_SOURCE_DISABLED_STUB = "SOURCE_DISABLED_STUB"
BLOCK_SOURCE_PORTAL_REFERENCE = "SOURCE_PORTAL_REFERENCE"
BLOCK_SOURCE_ADAPTER_MISSING = "SOURCE_ADAPTER_MISSING"
BLOCK_SOURCE_MANUAL_REFERENCE = "SOURCE_MANUAL_REFERENCE"
BLOCK_SOURCE_BLOCKED_SECRET = "SOURCE_BLOCKED_SECRET"
