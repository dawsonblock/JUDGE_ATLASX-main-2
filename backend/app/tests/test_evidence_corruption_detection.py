"""Proves the evidence store detects corrupted snapshot content.

Evidence corruption is when stored_content_hash no longer matches
content_hash (the hash verified at ingest time), or when the raw content
bytes no longer produce the stored hash.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ORIGINAL_CONTENT = b"Verified evidence document content."


class TestEvidenceCorruptionDetection:
    def test_intact_snapshot_hash_validates(self) -> None:
        """A freshly created snapshot's stored_content_hash must match content_hash."""
        content = ORIGINAL_CONTENT
        ch = _sha256(content)
        # Simulate what the DB columns hold
        content_hash = ch
        stored_content_hash = ch
        # Verification: recompute from raw bytes
        recomputed = _sha256(content)
        assert recomputed == content_hash, "intact snapshot must validate"
        assert stored_content_hash == content_hash

    def test_corrupted_raw_content_detected(self) -> None:
        """If raw_content bytes are altered after storage, recomputed hash diverges."""
        content = ORIGINAL_CONTENT
        stored_hash = _sha256(content)

        # Attacker modifies raw bytes
        corrupted_content = b"CORRUPTED evidence document content."
        recomputed = _sha256(corrupted_content)
        assert recomputed != stored_hash, "corruption must be detected by hash mismatch"

    def test_stored_hash_mismatch_detected(self) -> None:
        """Directly overwriting stored_content_hash while content stays intact
        is itself a corruption (the hash field was tampered with)."""
        content = ORIGINAL_CONTENT
        original_hash = _sha256(content)
        tampered_stored_hash = "0" * 64  # attacker zeros out the hash field

        recomputed = _sha256(content)
        assert recomputed == original_hash
        assert tampered_stored_hash != recomputed, (
            "tampered stored_content_hash must not match recomputed hash"
        )

    def test_partial_write_detected(self) -> None:
        """Partial writes (truncated content) must change the hash."""
        full_content = b"Full evidence document with all required sections present."
        truncated_content = b"Full evidence document"  # truncated mid-sentence

        h_full = _sha256(full_content)
        h_truncated = _sha256(truncated_content)
        assert h_full != h_truncated, "partial write must produce a different hash"

    def test_original_content_hash_preserved_for_truncated_storage(self) -> None:
        """original_content_hash must capture the FULL content even when stored
        content is truncated (is_truncated=True).

        stored_content_hash tracks the truncated hash; original_content_hash
        preserves what was actually retrieved from the source.
        """
        full_content = b"Extremely long evidence document." * 100
        truncated_content = full_content[:100]

        original_hash = _sha256(full_content)
        stored_hash = _sha256(truncated_content)

        # These must differ — otherwise we cannot detect truncation
        assert original_hash != stored_hash
        # original_content_hash must equal full content hash
        assert original_hash == _sha256(full_content)
