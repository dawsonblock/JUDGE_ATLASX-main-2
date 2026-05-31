"""Thread-safe runtime registry for canonical entity lookups.

Provides a per-process LRU-style cache that reduces repeated DB round-
trips when resolving the same canonical entity ID many times during a
single request or worker cycle.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.entities import CanonicalEntity

_DEFAULT_MAX_SIZE = 2048


class EntityRegistry:
    """Thread-safe in-memory cache keyed by canonical_entity.id.

    Uses an ordered dict to evict the least-recently-used entry when
    ``max_size`` is reached.
    """

    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[int, CanonicalEntity] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, entity_id: int, db: Session) -> CanonicalEntity | None:
        """Return the canonical entity for ``entity_id``, using cache.

        Args:
            entity_id: Primary key of the canonical entity.
            db:        SQLAlchemy session used for DB fallback.

        Returns:
            CanonicalEntity ORM object, or None if not found.
        """
        with self._lock:
            if entity_id in self._cache:
                # Move to end (most-recently-used position)
                self._cache.move_to_end(entity_id)
                return self._cache[entity_id]

        # DB fetch outside lock to avoid holding lock during IO
        from app.models.entities import (
            CanonicalEntity,
        )  # local import avoids circularity

        entity = db.get(CanonicalEntity, entity_id)

        if entity is not None:
            with self._lock:
                self._cache[entity_id] = entity
                self._cache.move_to_end(entity_id)
                if len(self._cache) > self._max_size:
                    self._cache.popitem(last=False)  # evict LRU

        return entity

    def put(self, entity: CanonicalEntity) -> None:
        """Insert or update a canonical entity in the cache."""
        with self._lock:
            self._cache[entity.id] = entity
            self._cache.move_to_end(entity.id)
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, entity_id: int) -> None:
        """Remove a single entity from the cache."""
        with self._lock:
            self._cache.pop(entity_id, None)

    def clear(self) -> None:
        """Evict all entries."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# Module-level singleton shared across all requests in a process
_registry = EntityRegistry()


def get_registry() -> EntityRegistry:
    """Return the process-global EntityRegistry singleton."""
    return _registry
