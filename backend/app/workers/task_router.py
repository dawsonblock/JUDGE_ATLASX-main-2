"""Task router — maps job names to handler callables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class RouteEntry:
    """Associates a job name with its handler function."""

    job_name: str
    handler: Callable[..., Any]
    description: str = ""


class TaskRouter:
    """Routes job names to registered handler callables."""

    def __init__(self) -> None:
        self._routes: dict[str, RouteEntry] = {}

    def register(
        self,
        job_name: str,
        handler: Callable[..., Any],
        description: str = "",
    ) -> None:
        """Register *handler* for *job_name*.  Overwrites any existing entry."""
        self._routes[job_name] = RouteEntry(
            job_name=job_name,
            handler=handler,
            description=description,
        )
        log.debug("TaskRouter: registered handler for %r", job_name)

    def route(self, job_name: str) -> Callable[..., Any] | None:
        """Return the handler for *job_name*, or ``None`` if not registered."""
        entry = self._routes.get(job_name)
        return entry.handler if entry else None

    def require_route(self, job_name: str) -> Callable[..., Any]:
        """Return the handler for *job_name*; raise ``KeyError`` if absent."""
        entry = self._routes.get(job_name)
        if entry is None:
            raise KeyError(f"No handler registered for job: {job_name!r}")
        return entry.handler

    def is_routed(self, job_name: str) -> bool:
        """Return ``True`` when *job_name* has a registered handler."""
        return job_name in self._routes

    def registered_names(self) -> list[str]:
        """Return sorted list of registered job names."""
        return sorted(self._routes)

    def deregister(self, job_name: str) -> bool:
        """Remove *job_name* from routing.  Returns ``True`` if it was present."""
        return self._routes.pop(job_name, None) is not None

    def __len__(self) -> int:
        return len(self._routes)
