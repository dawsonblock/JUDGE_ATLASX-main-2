"""Serializer contracts — typed field descriptors and serialisation specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    NULLABLE = "nullable"
    ANY = "any"


@dataclass(frozen=True)
class FieldDescriptor:
    """Declares a single serializable field."""

    name: str
    field_type: FieldType
    required: bool = True
    default: Any = None
    description: str = ""
    alias: Optional[str] = None

    @property
    def serialized_name(self) -> str:
        return self.alias if self.alias else self.name

    def is_optional(self) -> bool:
        return not self.required


@dataclass
class SerializerContract:
    """Declares which fields a serializer exposes and their constraints."""

    name: str
    fields: List[FieldDescriptor] = field(default_factory=list)
    version: str = "1.0"
    strict: bool = False  # if True, extra keys in input raise errors

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_field(self, descriptor: FieldDescriptor) -> None:
        if any(f.name == descriptor.name for f in self.fields):
            raise ValueError(
                f"Field '{descriptor.name}' already declared in '{self.name}'"
            )
        self.fields.append(descriptor)

    def remove_field(self, name: str) -> bool:
        for i, f in enumerate(self.fields):
            if f.name == name:
                del self.fields[i]
                return True
        return False

    def get_field(self, name: str) -> Optional[FieldDescriptor]:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def required_fields(self) -> List[FieldDescriptor]:
        return [f for f in self.fields if f.required]

    def optional_fields(self) -> List[FieldDescriptor]:
        return [f for f in self.fields if not f.required]

    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    def serialized_names(self) -> List[str]:
        return [f.serialized_name for f in self.fields]

    def has_field(self, name: str) -> bool:
        return any(f.name == name for f in self.fields)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_keys(self, data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Return (missing_required, extra_keys)."""
        declared = set(self.field_names())
        present = set(data.keys())
        missing = [f.name for f in self.required_fields() if f.name not in present]
        extra = sorted(present - declared)
        return missing, extra

    def is_valid(self, data: Dict[str, Any]) -> bool:
        missing, extra = self.validate_keys(data)
        if missing:
            return False
        if self.strict and extra:
            return False
        return True

    # ------------------------------------------------------------------
    # Serialise / deserialise
    # ------------------------------------------------------------------

    def serialize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Project data through contract; apply aliases and defaults."""
        out: Dict[str, Any] = {}
        for f in self.fields:
            if f.name in data:
                out[f.serialized_name] = data[f.name]
            elif not f.required:
                out[f.serialized_name] = f.default
        return out

    def deserialize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Reverse alias map; return {field.name: value}."""
        alias_to_name: Dict[str, str] = {f.serialized_name: f.name for f in self.fields}
        return {alias_to_name.get(k, k): v for k, v in data.items()}


__all__ = ["FieldType", "FieldDescriptor", "SerializerContract"]
