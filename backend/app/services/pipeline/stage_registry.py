"""Stage registry — register, lookup, and enumerate pipeline stage callables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# A stage is any callable that accepts a payload dict and returns a dict.
StageCallable = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class StageDescriptor:
    """Metadata for a registered pipeline stage."""

    name: str
    fn: StageCallable
    priority: int = 0  # lower number runs first
    tags: frozenset = field(default_factory=frozenset)
    enabled: bool = True

    def is_enabled(self) -> bool:
        return self.enabled


@dataclass
class StageRegistry:
    """Central registry for pipeline stage functions."""

    _stages: Dict[str, StageDescriptor] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        fn: StageCallable,
        *,
        priority: int = 0,
        tags: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> None:
        if name in self._stages:
            raise ValueError(f"Stage already registered: {name!r}")
        self._stages[name] = StageDescriptor(
            name=name,
            fn=fn,
            priority=priority,
            tags=frozenset(tags or []),
            enabled=enabled,
        )

    def unregister(self, name: str) -> bool:
        if name not in self._stages:
            return False
        del self._stages[name]
        return True

    def enable(self, name: str) -> bool:
        desc = self._stages.get(name)
        if desc is None:
            return False
        # frozen dataclass — replace the entry
        self._stages[name] = StageDescriptor(
            name=desc.name,
            fn=desc.fn,
            priority=desc.priority,
            tags=desc.tags,
            enabled=True,
        )
        return True

    def disable(self, name: str) -> bool:
        desc = self._stages.get(name)
        if desc is None:
            return False
        self._stages[name] = StageDescriptor(
            name=desc.name,
            fn=desc.fn,
            priority=desc.priority,
            tags=desc.tags,
            enabled=False,
        )
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[StageDescriptor]:
        return self._stages.get(name)

    def get_fn(self, name: str) -> Optional[StageCallable]:
        desc = self._stages.get(name)
        return desc.fn if desc else None

    def has(self, name: str) -> bool:
        return name in self._stages

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def all_stages(self) -> List[StageDescriptor]:
        """All registered stages, sorted by priority then name."""
        return sorted(self._stages.values(), key=lambda d: (d.priority, d.name))

    def enabled_stages(self) -> List[StageDescriptor]:
        return [d for d in self.all_stages() if d.enabled]

    def stages_with_tag(self, tag: str) -> List[StageDescriptor]:
        return [d for d in self.all_stages() if tag in d.tags]

    def stage_names(self) -> List[str]:
        return [d.name for d in self.all_stages()]

    def count(self) -> int:
        return len(self._stages)


__all__ = ["StageCallable", "StageDescriptor", "StageRegistry"]
