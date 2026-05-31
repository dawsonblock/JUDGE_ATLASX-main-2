"""Memory runtime package — Phase E.

Provides a deterministic, DB-free orchestration layer over the existing
memory primitives (extract_claims, invalidation, rebuild, retrieval).
"""

from __future__ import annotations

from app.memory.runtime.claim_lifecycle import (
    ClaimStatus,
    ClaimTransition,
    LifecyclePolicy,
)
from app.memory.runtime.state_machine import MemoryStateMachine, StateMachineError
from app.memory.runtime.diff_engine import ClaimDiff, DiffEngine, DiffResult
from app.memory.runtime.cache_policy import CacheEntry, CachePolicy, ClaimCache
from app.memory.runtime.rebuild_scheduler import (
    RebuildSchedule,
    RebuildScheduler,
    RebuildTrigger,
)
from app.memory.runtime.memory_metrics import MemoryMetricStat, MemoryMetrics
from app.memory.runtime.memory_runtime import MemoryRuntime, MemoryRuntimeConfig

__all__ = [
    "ClaimStatus",
    "ClaimTransition",
    "LifecyclePolicy",
    "MemoryStateMachine",
    "StateMachineError",
    "ClaimDiff",
    "DiffEngine",
    "DiffResult",
    "CacheEntry",
    "CachePolicy",
    "ClaimCache",
    "RebuildSchedule",
    "RebuildScheduler",
    "RebuildTrigger",
    "MemoryMetricStat",
    "MemoryMetrics",
    "MemoryRuntime",
    "MemoryRuntimeConfig",
]
