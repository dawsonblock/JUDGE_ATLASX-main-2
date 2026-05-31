"""Deterministic canonical ID generation.

Produces stable, collision-resistant identifiers for canonical entities
using SHA-256 hashing of normalised entity attributes.  All IDs are
deterministic so the same real-world entity always maps to the same string
regardless of which source first introduced it.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


class CanonicalIdError(ValueError):
    """Raised when canonical ID inputs are invalid."""


def normalize_entity_name(name: str) -> str:
    """Return a normalised form of an entity name suitable for comparison.

    Steps applied:
    1. Unicode NFKC normalisation (canonicalises unicode code points)
    2. Lowercase
    3. Strip leading/trailing whitespace
    4. Collapse interior whitespace runs to a single space
    5. Remove punctuation characters (hyphens between words kept as spaces)
    """
    if not name:
        raise CanonicalIdError("name must not be empty")

    # Unicode normalisation
    text = unicodedata.normalize("NFKC", name)
    text = text.lower().strip()

    # Replace common punctuation separators with spaces
    text = re.sub(r"['\"\-.]", " ", text)

    # Strip remaining non-alphanum/space characters
    text = re.sub(r"[^a-z0-9 ]", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        raise CanonicalIdError(f"name normalises to empty string: {name!r}")

    return text


def generate_canonical_id(
    entity_type: str,
    name: str,
    context: str | None = None,
) -> str:
    """Generate a stable 16-character hex canonical ID.

    The ID is the first 16 hex chars of SHA-256(entity_type|name|context).
    Collision probability is negligible for realistic dataset sizes.

    Args:
        entity_type: One of "judge", "court", "case", "defendant", "incident".
        name:        Raw display name of the entity.
        context:     Optional disambiguation context (e.g. court name, year).

    Returns:
        16-character lowercase hex string.

    Raises:
        CanonicalIdError: If entity_type or name are empty.
    """
    if not entity_type:
        raise CanonicalIdError("entity_type must not be empty")

    normalised = normalize_entity_name(name)
    parts = [entity_type.lower().strip(), normalised]
    if context:
        parts.append(context.lower().strip())

    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def canonical_id_from_external(source: str, external_id: str) -> str:
    """Derive a canonical ID from a known external identifier.

    Used when a source provides its own stable ID (e.g. CourtListener
    judge IDs) so we can produce a consistent canonical ID without
    requiring a name match.

    Args:
        source:      Source system name, e.g. "courtlistener".
        external_id: The external system's stable identifier.

    Returns:
        16-character lowercase hex string.
    """
    if not source or not external_id:
        raise CanonicalIdError("source and external_id must not be empty")

    payload = f"{source.lower().strip()}|{external_id.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
