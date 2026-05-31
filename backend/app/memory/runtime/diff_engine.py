"""Claim diff engine — compares two claim sets and reports changes.

Deterministic; no DB or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Sequence


class DiffKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class ClaimDiff:
    """A single claim-level diff entry."""

    claim_key: str
    kind: DiffKind
    old_value: str | None = None
    new_value: str | None = None

    def is_structural_change(self) -> bool:
        """True for added/removed (not modifications to text)."""
        return self.kind in (DiffKind.ADDED, DiffKind.REMOVED)


@dataclass
class DiffResult:
    """Aggregated diff between two claim snapshots."""

    added: FrozenSet[str] = field(default_factory=frozenset)
    removed: FrozenSet[str] = field(default_factory=frozenset)
    modified: FrozenSet[str] = field(default_factory=frozenset)
    unchanged: FrozenSet[str] = field(default_factory=frozenset)
    entries: tuple[ClaimDiff, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def change_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)

    @property
    def total_count(self) -> int:
        return self.change_count + len(self.unchanged)

    def summary(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "modified": len(self.modified),
            "unchanged": len(self.unchanged),
            "total": self.total_count,
        }


class DiffEngine:
    """Compares two collections of claim dicts by their claim_key.

    Each claim dict must contain at minimum:
      - ``claim_key``: str  (stable hash, the identity key)
      - ``normalized_text``: str  (content for modification detection)

    Use :meth:`diff` to get a :class:`DiffResult`.
    """

    def diff(
        self,
        old_claims: Sequence[dict],
        new_claims: Sequence[dict],
    ) -> DiffResult:
        """Compare *old_claims* to *new_claims* and return a :class:`DiffResult`."""
        old_map: Dict[str, dict] = {c["claim_key"]: c for c in old_claims}
        new_map: Dict[str, dict] = {c["claim_key"]: c for c in new_claims}

        old_keys = set(old_map)
        new_keys = set(new_map)

        added_keys = new_keys - old_keys
        removed_keys = old_keys - new_keys
        common_keys = old_keys & new_keys

        modified_keys: set[str] = set()
        unchanged_keys: set[str] = set()

        for key in common_keys:
            old_text = old_map[key].get("normalized_text", "")
            new_text = new_map[key].get("normalized_text", "")
            if old_text != new_text:
                modified_keys.add(key)
            else:
                unchanged_keys.add(key)

        entries: list[ClaimDiff] = []
        for key in sorted(added_keys):
            entries.append(
                ClaimDiff(
                    claim_key=key,
                    kind=DiffKind.ADDED,
                    new_value=new_map[key].get("normalized_text"),
                )
            )
        for key in sorted(removed_keys):
            entries.append(
                ClaimDiff(
                    claim_key=key,
                    kind=DiffKind.REMOVED,
                    old_value=old_map[key].get("normalized_text"),
                )
            )
        for key in sorted(modified_keys):
            entries.append(
                ClaimDiff(
                    claim_key=key,
                    kind=DiffKind.MODIFIED,
                    old_value=old_map[key].get("normalized_text"),
                    new_value=new_map[key].get("normalized_text"),
                )
            )
        for key in sorted(unchanged_keys):
            entries.append(ClaimDiff(claim_key=key, kind=DiffKind.UNCHANGED))

        return DiffResult(
            added=frozenset(added_keys),
            removed=frozenset(removed_keys),
            modified=frozenset(modified_keys),
            unchanged=frozenset(unchanged_keys),
            entries=tuple(entries),
        )

    def key_set_diff(
        self, old_keys: FrozenSet[str], new_keys: FrozenSet[str]
    ) -> dict[str, FrozenSet[str]]:
        """Lightweight key-only diff (no text comparison)."""
        return {
            "added": new_keys - old_keys,
            "removed": old_keys - new_keys,
            "common": old_keys & new_keys,
        }
