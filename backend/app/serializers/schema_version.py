"""Schema versioning — track and negotiate serializer schema versions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SchemaVersion:
    """Immutable semantic version (major.minor.patch)."""

    major: int
    minor: int
    patch: int = 0

    @classmethod
    def parse(cls, version_str: str) -> "SchemaVersion":
        parts = version_str.split(".")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(f"Invalid version string: '{version_str}'")
        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2]) if len(parts) == 3 else 0
        except ValueError:
            raise ValueError(f"Non-integer version component in: '{version_str}'")
        if major < 0 or minor < 0 or patch < 0:
            raise ValueError("Version components must be non-negative")
        return cls(major=major, minor=minor, patch=patch)

    def is_compatible_with(self, other: "SchemaVersion") -> bool:
        """True when same major version and this minor >= other minor."""
        return self.major == other.major and self.minor >= other.minor

    def is_breaking_from(self, other: "SchemaVersion") -> bool:
        """True when major versions differ."""
        return self.major != other.major

    def bump_major(self) -> "SchemaVersion":
        return SchemaVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> "SchemaVersion":
        return SchemaVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SchemaVersion":
        return SchemaVersion(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "SchemaVersion") -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other: "SchemaVersion") -> bool:
        return self == other or self < other

    def __gt__(self, other: "SchemaVersion") -> bool:
        return not self <= other

    def __ge__(self, other: "SchemaVersion") -> bool:
        return not self < other


@dataclass
class VersionedSchema:
    """Associates a schema name with a version and optional changelog."""

    schema_name: str
    version: SchemaVersion
    changelog: str = ""
    deprecated: bool = False

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema_name": self.schema_name,
            "version": str(self.version),
            "deprecated": self.deprecated,
            "changelog": self.changelog,
        }


@dataclass
class SchemaVersionRegistry:
    """Tracks all registered schema versions and selects the best match."""

    _schemas: Dict[str, List[VersionedSchema]] = field(default_factory=dict, init=False)

    def register(self, schema: VersionedSchema) -> None:
        name = schema.schema_name
        if name not in self._schemas:
            self._schemas[name] = []
        # Reject exact-duplicate versions
        for existing in self._schemas[name]:
            if existing.version == schema.version:
                raise ValueError(
                    f"Version {schema.version} already registered for '{name}'"
                )
        self._schemas[name].append(schema)
        self._schemas[name].sort(key=lambda s: s.version)

    def latest(self, schema_name: str) -> Optional[VersionedSchema]:
        versions = self._schemas.get(schema_name)
        if not versions:
            return None
        return versions[-1]

    def get(
        self, schema_name: str, version: SchemaVersion
    ) -> Optional[VersionedSchema]:
        for vs in self._schemas.get(schema_name, []):
            if vs.version == version:
                return vs
        return None

    def negotiate(
        self, schema_name: str, requested: SchemaVersion
    ) -> Optional[VersionedSchema]:
        """Return the highest non-deprecated schema compatible with requested."""
        candidates = [
            vs
            for vs in self._schemas.get(schema_name, [])
            if not vs.deprecated and vs.version.is_compatible_with(requested)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda vs: vs.version)

    def all_versions(self, schema_name: str) -> List[VersionedSchema]:
        return list(self._schemas.get(schema_name, []))

    def schema_names(self) -> List[str]:
        return sorted(self._schemas.keys())

    def deprecate(self, schema_name: str, version: SchemaVersion) -> bool:
        vs = self.get(schema_name, version)
        if vs is None:
            return False
        vs.deprecated = True
        return True


__all__ = ["SchemaVersion", "VersionedSchema", "SchemaVersionRegistry"]
