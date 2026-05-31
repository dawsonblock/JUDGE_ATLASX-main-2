"""Service locator — lightweight in-process dependency registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceBinding:
    interface: str  # canonical name / key
    instance: Any
    singleton: bool = True
    tags: frozenset = field(default_factory=frozenset)


@dataclass
class ServiceLocator:
    """Register and resolve service instances by name or type."""

    _bindings: Dict[str, ServiceBinding] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        interface: str,
        instance: Any,
        *,
        singleton: bool = True,
        tags: Optional[List[str]] = None,
        overwrite: bool = False,
    ) -> None:
        if interface in self._bindings and not overwrite:
            raise ValueError(f"Service already registered: {interface!r}")
        self._bindings[interface] = ServiceBinding(
            interface=interface,
            instance=instance,
            singleton=singleton,
            tags=frozenset(tags or []),
        )

    def unregister(self, interface: str) -> bool:
        return bool(self._bindings.pop(interface, None))

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, interface: str) -> Any:
        binding = self._bindings.get(interface)
        if binding is None:
            raise KeyError(f"No service registered for: {interface!r}")
        return binding.instance

    def try_resolve(self, interface: str, default: Any = None) -> Any:
        binding = self._bindings.get(interface)
        return binding.instance if binding else default

    def resolve_by_type(self, cls: Type[T]) -> T:
        """Find first registered instance that is an instance of `cls`."""
        for binding in self._bindings.values():
            if isinstance(binding.instance, cls):
                return binding.instance  # type: ignore[return-value]
        raise KeyError(f"No service registered for type: {cls!r}")

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def is_registered(self, interface: str) -> bool:
        return interface in self._bindings

    def registered_names(self) -> List[str]:
        return sorted(self._bindings)

    def with_tag(self, tag: str) -> List[ServiceBinding]:
        return [b for b in self._bindings.values() if tag in b.tags]

    def count(self) -> int:
        return len(self._bindings)

    def clear(self) -> None:
        self._bindings.clear()


__all__ = ["ServiceBinding", "ServiceLocator"]
