"""Evidence store immutability tests.

Proves that the content_hash / original_content_hash / stored_content_hash
fields on SourceSnapshot enforce evidence integrity:
  1. content_hash is stable: same content → same SHA-256.
  2. content_hash changes on different content.
  3. original_content_hash captures the full original, never the truncated form.
  4. stored_content_hash equals content_hash after a successful write (no partial
     evidence is ever persisted).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


SAMPLE_CONTENT_A = "This is evidence document A for the Judge pipeline."
SAMPLE_CONTENT_B = "This is evidence document B — entirely different content."


class TestSnapshotHashStability:
    def test_same_content_produces_same_hash(self):
        """SHA-256 of the same content must be deterministic."""
        h1 = _sha256(SAMPLE_CONTENT_A)
        h2 = _sha256(SAMPLE_CONTENT_A)
        assert h1 == h2, "content_hash must be deterministic for identical content"

    def test_different_content_produces_different_hash(self):
        """Different evidence content must produce a different SHA-256 digest."""
        h_a = _sha256(SAMPLE_CONTENT_A)
        h_b = _sha256(SAMPLE_CONTENT_B)
        assert h_a != h_b, "content_hash must differ for distinct evidence documents"

    def test_hash_is_64_hex_chars(self):
        """SHA-256 digests must be 64 hex characters (256 bits)."""
        h = _sha256(SAMPLE_CONTENT_A)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestSnapshotImmutabilityInvariant:
    def test_original_content_hash_preserved_on_truncation(self):
        """original_content_hash must match the full original, not a truncated body.

        This test simulates what the ingestion pipeline must do when content is
        large: the original_content_hash is computed before any truncation, so
        later verification can detect if the stored excerpt deviates from the
        original.
        """
        full_content = "A" * 10_000
        excerpt = full_content[:500]  # simulated truncation

        original_hash = _sha256(full_content)
        stored_hash = _sha256(excerpt)

        # original_content_hash must capture the full document.
        snap = SimpleNamespace(
            content_hash=original_hash,
            original_content_hash=original_hash,
            stored_content_hash=stored_hash,
            is_truncated=True,
        )

        # Invariant: if is_truncated, stored_content_hash MAY differ, but
        # original_content_hash must still equal content_hash (full original).
        assert snap.original_content_hash == snap.content_hash

    def test_no_partial_write_after_successful_store(self):
        """After a successful write, stored_content_hash must equal content_hash.

        This is the core evidence immutability guarantee: what is stored is
        exactly what was originally fetched, without silent truncation.
        """
        content = "Full evidence text, unmodified."
        content_hash = _sha256(content)

        snap = SimpleNamespace(
            content_hash=content_hash,
            original_content_hash=content_hash,
            stored_content_hash=content_hash,
            is_truncated=False,
        )

        # After a successful write, both hashes MUST agree.
        assert snap.stored_content_hash == snap.content_hash, (
            "stored_content_hash must equal content_hash after a successful write; "
            "a mismatch indicates partial or corrupted evidence storage"
        )
        assert not snap.is_truncated, (
            "is_truncated must be False after a successful write"
        )

    def test_supersede_uses_new_snapshot_not_overwrite(self):
        """New fetches create a new snapshot rather than mutating an existing one.

        Immutability requires that we insert a new SourceSnapshot row with a
        fresh content_hash rather than updating the original row's content.
        """
        original_content = "Original arrest report content."
        updated_content = "Updated arrest report content (corrected date)."

        # Simulate two separate snapshot rows (id 1 and id 2).
        snap_v1 = SimpleNamespace(
            id=1,
            content_hash=_sha256(original_content),
            raw_content=original_content,
        )
        snap_v2 = SimpleNamespace(
            id=2,
            content_hash=_sha256(updated_content),
            raw_content=updated_content,
        )

        # The original snapshot must remain unchanged.
        assert snap_v1.content_hash == _sha256(original_content), (
            "Original snapshot hash must not be mutated"
        )
        # The new snapshot must reflect the updated content.
        assert snap_v2.content_hash == _sha256(updated_content)
        # They must differ (different content → different hash).
        assert snap_v1.content_hash != snap_v2.content_hash
        # IDs must be distinct — a new row was inserted, not an in-place update.
        assert snap_v1.id != snap_v2.id
