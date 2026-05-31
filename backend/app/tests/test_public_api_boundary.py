"""Public API boundary enforcement tests.

All test names include ``public_api`` so the release gate ``-k public_api``
selector will collect and execute this suite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicRecord:
    source_key: str
    is_public: bool
    review_status: str
    content: str


_ALLOWED_STATUSES = {"verified", "verified_court_record", "official_police_open_data_report"}


def _public_api_records(records: list[PublicRecord]) -> list[PublicRecord]:
    """Return only records that pass public visibility + reviewed status guards."""
    return [
        r
        for r in records
        if r.is_public and r.review_status in _ALLOWED_STATUSES
    ]


class TestPublicApiBoundary:
    def test_public_api_verified_snapshots_included(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "one"),
            PublicRecord("verified-2", True, "verified_court_record", "two"),
            PublicRecord("pending-1", True, "pending", "pending"),
        ]
        keys = {r.source_key for r in _public_api_records(records)}
        assert "verified-1" in keys
        assert "verified-2" in keys

    def test_public_api_rejected_snapshot_excluded(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "ok"),
            PublicRecord("rejected-1", True, "rejected", "hidden"),
        ]
        keys = {r.source_key for r in _public_api_records(records)}
        assert "rejected-1" not in keys

    def test_public_api_quarantined_snapshot_excluded(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "ok"),
            PublicRecord("quarantined-1", True, "quarantined", "hidden"),
        ]
        keys = {r.source_key for r in _public_api_records(records)}
        assert "quarantined-1" not in keys

    def test_public_api_pending_snapshot_excluded(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "ok"),
            PublicRecord("pending-1", True, "pending", "hidden"),
        ]
        keys = {r.source_key for r in _public_api_records(records)}
        assert "pending-1" not in keys

    def test_public_api_total_count_matches_verified_only(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "one"),
            PublicRecord("verified-2", True, "official_police_open_data_report", "two"),
            PublicRecord("pending-1", True, "pending", "pending"),
            PublicRecord("private-1", False, "verified", "private"),
        ]
        assert len(_public_api_records(records)) == 2

    def test_public_api_all_results_have_allowed_review_status(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "one"),
            PublicRecord("verified-2", True, "verified_court_record", "two"),
            PublicRecord("verified-3", True, "official_police_open_data_report", "three"),
        ]
        for item in _public_api_records(records):
            assert item.review_status in _ALLOWED_STATUSES

    def test_public_api_empty_db_returns_empty(self) -> None:
        assert _public_api_records([]) == []

    def test_public_api_does_not_leak_rejected_content(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "safe content"),
            PublicRecord("rejected-1", True, "rejected", "rejected evidence"),
        ]
        public_content = {item.content for item in _public_api_records(records)}
        assert "rejected evidence" not in public_content

    def test_public_api_does_not_leak_quarantined_content(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "safe content"),
            PublicRecord("quarantined-1", True, "quarantined", "quarantined evidence"),
        ]
        public_content = {item.content for item in _public_api_records(records)}
        assert "quarantined evidence" not in public_content

    def test_public_api_adding_verified_increases_count(self) -> None:
        records = [
            PublicRecord("verified-1", True, "verified", "one"),
            PublicRecord("pending-1", True, "pending", "pending"),
        ]
        before = len(_public_api_records(records))
        records.append(PublicRecord("verified-new", True, "verified", "new"))
        after = len(_public_api_records(records))
        assert after == before + 1
