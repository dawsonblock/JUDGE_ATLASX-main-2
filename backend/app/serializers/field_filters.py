"""Field filters — select, mask, and transform serializer output fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set


@dataclass(frozen=True)
class FieldMask:
    """Immutable set of allowed field names."""

    allowed: FrozenSet[str]

    @classmethod
    def from_list(cls, names: List[str]) -> "FieldMask":
        return cls(allowed=frozenset(names))

    def includes(self, name: str) -> bool:
        return name in self.allowed

    def excludes(self, name: str) -> bool:
        return name not in self.allowed

    def intersect(self, other: "FieldMask") -> "FieldMask":
        return FieldMask(allowed=self.allowed & other.allowed)

    def union(self, other: "FieldMask") -> "FieldMask":
        return FieldMask(allowed=self.allowed | other.allowed)

    def apply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if k in self.allowed}

    def __len__(self) -> int:
        return len(self.allowed)


@dataclass
class FieldRedactor:
    """Replaces sensitive field values with a redaction placeholder."""

    sensitive_fields: Set[str] = field(default_factory=set)
    placeholder: str = "[REDACTED]"

    def add(self, *names: str) -> None:
        self.sensitive_fields.update(names)

    def remove(self, name: str) -> bool:
        if name in self.sensitive_fields:
            self.sensitive_fields.discard(name)
            return True
        return False

    def is_sensitive(self, name: str) -> bool:
        return name in self.sensitive_fields

    def redact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: (self.placeholder if k in self.sensitive_fields else v)
            for k, v in data.items()
        }

    def redact_value(self, name: str, value: Any) -> Any:
        return self.placeholder if name in self.sensitive_fields else value


Transform = Callable[[Any], Any]


@dataclass
class FieldTransformer:
    """Applies per-field transform functions to serializer output."""

    _transforms: Dict[str, Transform] = field(default_factory=dict, init=False)

    def register(self, field_name: str, fn: Transform) -> None:
        self._transforms[field_name] = fn

    def unregister(self, field_name: str) -> bool:
        if field_name in self._transforms:
            del self._transforms[field_name]
            return True
        return False

    def has_transform(self, field_name: str) -> bool:
        return field_name in self._transforms

    def apply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in data.items():
            fn = self._transforms.get(k)
            out[k] = fn(v) if fn is not None else v
        return out

    def transform_value(self, field_name: str, value: Any) -> Any:
        fn = self._transforms.get(field_name)
        return fn(value) if fn is not None else value

    @property
    def registered_fields(self) -> List[str]:
        return sorted(self._transforms.keys())


@dataclass
class FieldFilterPipeline:
    """Compose mask → redact → transform in order."""

    mask: Optional[FieldMask] = None
    redactor: Optional[FieldRedactor] = None
    transformer: Optional[FieldTransformer] = None

    def apply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)
        if self.mask is not None:
            result = self.mask.apply(result)
        if self.redactor is not None:
            result = self.redactor.redact(result)
        if self.transformer is not None:
            result = self.transformer.apply(result)
        return result


__all__ = [
    "FieldMask",
    "FieldRedactor",
    "FieldTransformer",
    "FieldFilterPipeline",
]
