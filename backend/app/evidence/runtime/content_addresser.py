"""Content addresser — computes and indexes content addresses.

A *content address* uniquely identifies a blob by its cryptographic hash and
size.  No I/O or DB; works purely in-process with raw bytes or pre-computed
digests.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ContentAddress:
    """Immutable content address for a single evidence blob.

    Attributes
    ----------
    hash_hex:
        SHA-256 hex digest (64 lowercase chars).
    size:
        Byte length of the original content.
    mime:
        Optional MIME type hint (e.g. ``"text/html"``).
    """

    hash_hex: str
    size: int
    mime: Optional[str] = None

    def short_hash(self, n: int = 16) -> str:
        """Return the first *n* chars of :attr:`hash_hex`."""
        return self.hash_hex[:n]

    def matches(self, other: "ContentAddress") -> bool:
        """True when both addresses point to the same content (hash == hash)."""
        return self.hash_hex == other.hash_hex

    def __str__(self) -> str:
        return f"sha256:{self.short_hash(12)}…[{self.size}B]"


class ContentAddresser:
    """Computes :class:`ContentAddress` values and maintains a registry.

    The registry maps *snapshot_id* → :class:`ContentAddress` so the runtime
    can look up existing addresses without re-hashing.
    """

    def __init__(self) -> None:
        self._registry: Dict[int, ContentAddress] = {}

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def address_of(self, content: bytes, mime: str | None = None) -> ContentAddress:
        """Return the :class:`ContentAddress` for *content*."""
        hex_digest = hashlib.sha256(content).hexdigest()
        return ContentAddress(hash_hex=hex_digest, size=len(content), mime=mime)

    def address_of_hex(
        self, hash_hex: str, size: int, mime: str | None = None
    ) -> ContentAddress:
        """Build a :class:`ContentAddress` from a pre-computed hex digest."""
        if len(hash_hex) != 64:
            raise ValueError(f"Expected 64-char hex digest, got {len(hash_hex)}")
        return ContentAddress(hash_hex=hash_hex, size=size, mime=mime)

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def register(self, snapshot_id: int, address: ContentAddress) -> None:
        """Associate *snapshot_id* with *address* in the registry."""
        self._registry[snapshot_id] = address

    def lookup(self, snapshot_id: int) -> Optional[ContentAddress]:
        """Return the registered address for *snapshot_id* or None."""
        return self._registry.get(snapshot_id)

    def deregister(self, snapshot_id: int) -> bool:
        """Remove the registry entry for *snapshot_id*.  Returns True if found."""
        if snapshot_id in self._registry:
            del self._registry[snapshot_id]
            return True
        return False

    def has(self, snapshot_id: int) -> bool:
        """True if *snapshot_id* is registered."""
        return snapshot_id in self._registry

    @property
    def registry_size(self) -> int:
        return len(self._registry)

    def find_duplicates(self) -> Dict[str, list[int]]:
        """Return a mapping of hash_hex → [snapshot_ids] for hashes that appear >1."""
        by_hash: Dict[str, list[int]] = {}
        for sid, addr in self._registry.items():
            by_hash.setdefault(addr.hash_hex, []).append(sid)
        return {h: ids for h, ids in by_hash.items() if len(ids) > 1}

    def clear(self) -> int:
        """Remove all registry entries.  Returns count removed."""
        count = len(self._registry)
        self._registry.clear()
        return count
