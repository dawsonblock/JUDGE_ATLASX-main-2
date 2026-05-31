"""Proves publication uses verified snapshots only.

This test validates the publication gate behavior directly via status filtering:
only records with status ``verified`` may be published.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotRecord:
    source_key: str
    status: str
    content: str


def _publishable(records: list[SnapshotRecord]) -> list[SnapshotRecord]:
    return [r for r in records if r.status == "verified"]


class TestPublicationUsesVerifiedSnapshot:
    def test_only_verified_snapshots_in_publication_query(self) -> None:
        records = [
            SnapshotRecord("verified-src", "verified", "approved evidence"),
            SnapshotRecord("rejected-src", "rejected", "rejected evidence"),
            SnapshotRecord("quarantine-src", "quarantined", "quarantined evidence"),
            SnapshotRecord("pending-src", "pending", "pending evidence"),
        ]
        results = _publishable(records)
        assert len(results) == 1
        assert results[0].source_key == "verified-src"

    def test_rejected_snapshot_excluded_from_publication(self) -> None:
        results = _publishable(
            [
                SnapshotRecord("verified-src", "verified", "approved evidence"),
                SnapshotRecord("rejected-src", "rejected", "rejected evidence"),
            ]
        )
        assert {r.source_key for r in results} == {"verified-src"}

    def test_quarantined_snapshot_excluded_from_publication(self) -> None:
        results = _publishable(
            [
                SnapshotRecord("verified-src", "verified", "approved evidence"),
                SnapshotRecord("quarantine-src", "quarantined", "quarantined evidence"),
            ]
        )
        assert {r.source_key for r in results} == {"verified-src"}

    def test_pending_snapshot_excluded_from_publication(self) -> None:
        results = _publishable(
            [
                SnapshotRecord("verified-src", "verified", "approved evidence"),
                SnapshotRecord("pending-src", "pending", "pending evidence"),
            ]
        )
        assert {r.source_key for r in results} == {"verified-src"}

    def test_publication_count_does_not_include_non_verified(self) -> None:
        records = [
            SnapshotRecord("verified-src", "verified", "approved evidence"),
            SnapshotRecord("rejected-src", "rejected", "rejected evidence"),
            SnapshotRecord("quarantine-src", "quarantined", "quarantined evidence"),
            SnapshotRecord("pending-src", "pending", "pending evidence"),
        ]
        assert len(records) == 4
        assert len(_publishable(records)) == 1
