"""Job type registry — maps job names to handler callables with metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class JobSpec:
    """Immutable descriptor for a registered job type."""

    name: str
    handler: Callable[..., Any]
    max_attempts: int = 3
    timeout_seconds: float = 300.0
    priority: int = 5  # 1 = highest, 10 = lowest


class JobRegistry:
    """Central registry mapping job names to JobSpec objects."""

    def __init__(self) -> None:
        self._specs: dict[str, JobSpec] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        max_attempts: int = 3,
        timeout_seconds: float = 300.0,
        priority: int = 5,
    ) -> JobSpec:
        """Register a job type.  Re-registering the same name overwrites."""
        spec = JobSpec(
            name=name,
            handler=handler,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        self._specs[name] = spec
        return spec

    def get(self, name: str) -> JobSpec | None:
        """Return the JobSpec for *name*, or ``None`` if not registered."""
        return self._specs.get(name)

    def require(self, name: str) -> JobSpec:
        """Return the JobSpec for *name*; raise ``KeyError`` if absent."""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"No job type registered: {name!r}")
        return spec

    def list_names(self) -> list[str]:
        """Return alphabetically sorted list of registered job names."""
        return sorted(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: object) -> bool:
        return name in self._specs


# ---------------------------------------------------------------------------
# Module-level default registry (singleton)
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY = JobRegistry()


def get_default_registry() -> JobRegistry:
    """Return the process-wide default job registry."""
    return _DEFAULT_REGISTRY
