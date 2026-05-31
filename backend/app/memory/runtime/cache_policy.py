"""Claim cache with TTL and eviction policy.

Deterministic; no DB or I/O.  Uses a monotonic counter instead of
wall-clock time so tests are fully reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvictionStrategy(str, Enum):
    LRU = "lru"  # evict least-recently-used
    FIFO = "fifo"  # evict oldest inserted


@dataclass
class CachePolicy:
    """Configuration for a :class:`ClaimCache`.

    Attributes
    ----------
    max_entries:
        Maximum number of entries before eviction triggers.
    ttl_ticks:
        Entries older than this many *ticks* are considered expired.
        Set to 0 or None to disable TTL.
    eviction_strategy:
        Which eviction strategy to use when the cache is full.
    """

    max_entries: int = 256
    ttl_ticks: int | None = 60
    eviction_strategy: EvictionStrategy = EvictionStrategy.LRU

    def is_ttl_enabled(self) -> bool:
        return self.ttl_ticks is not None and self.ttl_ticks > 0


@dataclass
class CacheEntry:
    """A single cached claim payload."""

    key: str
    value: Any
    inserted_tick: int
    last_accessed_tick: int

    def age(self, current_tick: int) -> int:
        return current_tick - self.inserted_tick

    def is_expired(self, current_tick: int, ttl_ticks: int) -> bool:
        return self.age(current_tick) >= ttl_ticks


class ClaimCache:
    """In-memory LRU/FIFO cache for claim payloads.

    The cache is keyed on *claim_key* (stable hash string).  A monotonic
    tick counter is used throughout so behaviour is fully deterministic.

    Parameters
    ----------
    policy:
        Cache configuration.
    """

    def __init__(self, policy: CachePolicy | None = None) -> None:
        self.policy = policy or CachePolicy()
        self._store: Dict[str, CacheEntry] = {}
        self._tick: int = 0
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    # ------------------------------------------------------------------
    # Tick management
    # ------------------------------------------------------------------

    def advance_tick(self, by: int = 1) -> int:
        """Advance the internal tick counter by *by* and return new value."""
        self._tick += by
        return self._tick

    @property
    def current_tick(self) -> int:
        return self._tick

    # ------------------------------------------------------------------
    # Cache operations
    # ------------------------------------------------------------------

    def put(self, key: str, value: Any) -> None:
        """Insert or update *key* in the cache."""
        if key in self._store:
            entry = self._store[key]
            entry.value = value
            entry.last_accessed_tick = self._tick
            return

        # Evict if at capacity
        while len(self._store) >= self.policy.max_entries:
            self._evict_one()

        self._store[key] = CacheEntry(
            key=key,
            value=value,
            inserted_tick=self._tick,
            last_accessed_tick=self._tick,
        )

    def get(self, key: str) -> Any | None:
        """Return cached value for *key* or None if absent/expired."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        if self.policy.is_ttl_enabled() and entry.is_expired(self._tick, self.policy.ttl_ticks):  # type: ignore[arg-type]
            del self._store[key]
            self._misses += 1
            return None

        entry.last_accessed_tick = self._tick
        self._hits += 1
        return entry.value

    def evict(self, key: str) -> bool:
        """Explicitly remove *key*.  Returns True if it was present."""
        if key in self._store:
            del self._store[key]
            self._evictions += 1
            return True
        return False

    def purge_expired(self) -> int:
        """Remove all TTL-expired entries.  Returns count removed."""
        if not self.policy.is_ttl_enabled():
            return 0
        expired = [
            k
            for k, e in self._store.items()
            if e.is_expired(self._tick, self.policy.ttl_ticks)  # type: ignore[arg-type]
        ]
        for k in expired:
            del self._store[k]
            self._evictions += 1
        return len(expired)

    def clear(self) -> int:
        """Remove all entries.  Returns count removed."""
        count = len(self._store)
        self._store.clear()
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def evictions(self) -> int:
        return self._evictions

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def entries(self) -> List[CacheEntry]:
        return list(self._store.values())

    # ------------------------------------------------------------------
    # Internal eviction logic
    # ------------------------------------------------------------------

    def _evict_one(self) -> None:
        if not self._store:
            return
        if self.policy.eviction_strategy == EvictionStrategy.LRU:
            victim = min(self._store.values(), key=lambda e: e.last_accessed_tick)
        else:  # FIFO
            victim = min(self._store.values(), key=lambda e: e.inserted_tick)
        del self._store[victim.key]
        self._evictions += 1
