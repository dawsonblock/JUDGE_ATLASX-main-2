"""Evidence vault runtime package.

Deterministic in-process runtime layer on top of the existing
``app.evidence`` DB-bound primitives.  No I/O, no SQLAlchemy.
"""

from __future__ import annotations

from app.evidence.runtime.content_addresser import ContentAddress, ContentAddresser
from app.evidence.runtime.integrity_checker import IntegrityResult, IntegrityChecker
from app.evidence.runtime.retention_policy import (
    RetentionTier,
    RetentionPolicy,
    RetentionSchedule,
)
from app.evidence.runtime.snapshot_lifecycle import SnapshotState, SnapshotLifecycle
from app.evidence.runtime.vault_metrics import VaultStat, VaultMetrics
from app.evidence.runtime.vault_runtime import VaultRuntimeConfig, VaultRuntime

__all__ = [
    "ContentAddress",
    "ContentAddresser",
    "IntegrityResult",
    "IntegrityChecker",
    "RetentionTier",
    "RetentionPolicy",
    "RetentionSchedule",
    "SnapshotState",
    "SnapshotLifecycle",
    "VaultStat",
    "VaultMetrics",
    "VaultRuntimeConfig",
    "VaultRuntime",
]
