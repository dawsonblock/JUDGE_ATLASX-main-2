"""Tests for the archive export and custody-grade verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from app.archive.verify_export import verify_jsonl_export


def _write_jsonl(records: list[dict], path: Path) -> None:
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# ── Snapshot verification ─────────────────────────────────────────────────────


class TestSnapshotVerification:
    def _valid_snapshot(self, **overrides) -> dict:
        base = {
            "record_id": "1",
            "source_key": "federal_court_canada",
            "source_url": "https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do",
            "captured_at": "2026-05-06T00:00:00+00:00",
            "content_hash": "abc123def456",
            "evidence_type": "court_decision",
            "review_status": "captured",
            "publication_status": "unpublished",
            "payload": {"extracted_text": "sample"},
        }
        base.update(overrides)
        return base

    def test_valid_snapshot_passes(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            f.write(json.dumps(self._valid_snapshot()) + "\n")
        result = verify_jsonl_export(path)
        assert result.ok  # nosec B101
        assert result.valid_records == 1  # nosec B101
        assert result.invalid_records == 0

    def test_missing_content_hash_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            record = self._valid_snapshot()
            del record["content_hash"]
            f.write(json.dumps(record) + "\n")
        result = verify_jsonl_export(path)
        assert not result.ok
        assert result.invalid_records == 1
        assert any("content_hash" in e for e in result.errors)

    def test_empty_content_hash_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            f.write(json.dumps(self._valid_snapshot(content_hash="")) + "\n")
        result = verify_jsonl_export(path)
        assert not result.ok
        assert result.invalid_records == 1

    def test_missing_source_key_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            record = self._valid_snapshot()
            del record["source_key"]
            f.write(json.dumps(record) + "\n")
        result = verify_jsonl_export(path)
        assert not result.ok

    def test_missing_evidence_type_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            record = self._valid_snapshot()
            del record["evidence_type"]
            f.write(json.dumps(record) + "\n")
        result = verify_jsonl_export(path)
        assert not result.ok

    def test_payload_not_dict_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            f.write(
                json.dumps(self._valid_snapshot(payload=["not", "a", "dict"])) + "\n"
            )
        result = verify_jsonl_export(path)
        assert not result.ok

    def test_empty_file_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
        result = verify_jsonl_export(path)
        assert not result.ok
        assert result.total_lines == 0

    def test_file_not_found_fails(self) -> None:
        result = verify_jsonl_export(Path("/tmp/nonexistent_archive_xyz.jsonl"))
        assert not result.ok
        assert any("not found" in e.lower() for e in result.errors)

    def test_multiple_valid_records(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            for i in range(5):
                r = self._valid_snapshot(record_id=str(i), content_hash=f"hash{i}")
                f.write(json.dumps(r) + "\n")
        result = verify_jsonl_export(path)
        assert result.ok
        assert result.valid_records == 5

    def test_mixed_valid_invalid(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            f.write(json.dumps(self._valid_snapshot(record_id="1")) + "\n")
            f.write(json.dumps({"record_id": "2"}) + "\n")  # missing fields
            f.write(json.dumps(self._valid_snapshot(record_id="3")) + "\n")
        result = verify_jsonl_export(path)
        assert not result.ok
        assert result.valid_records == 2
        assert result.invalid_records == 1

    def test_canonical_archive_publication_status_values_are_valid(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = Path(f.name)
            f.write(
                json.dumps(
                    self._valid_snapshot(
                        publication_status="restricted",
                    )
                )
                + "\n"
            )
        result = verify_jsonl_export(path)
        assert result.ok  # nosec B101
        assert result.valid_records == 1  # nosec B101


# ── Memory claim verification ─────────────────────────────────────────────────


class TestMemoryClaimVerification:
    def _valid_memory(self, **overrides) -> dict:
        base = {
            "record_id": "1",
            "claim_key": "abc123",
            "claim_type": "court_decision_summary",
            "claim_text": "The court ruled in favour of the applicant.",
            "status": "active",
            "confidence_score": 0.85,
            "created_at": "2026-05-06T00:00:00+00:00",
            "evidence_snapshot_ids": ["42"],
            "payload": {"entity_id": 1},
        }
        base.update(overrides)
        return base

    def _memory_path(self, records: list[dict]) -> Path:
        with tempfile.NamedTemporaryFile(
            suffix="_memory_claims.jsonl", mode="w", delete=False
        ) as f:
            path = Path(f.name)
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path

    def test_valid_memory_claim_passes(self) -> None:
        path = self._memory_path([self._valid_memory()])
        result = verify_jsonl_export(path)
        assert result.ok
        assert result.valid_records == 1

    def test_missing_claim_key_fails(self) -> None:
        record = self._valid_memory()
        del record["claim_key"]
        path = self._memory_path([record])
        result = verify_jsonl_export(path)
        assert not result.ok

    def test_evidence_snapshot_ids_not_list_fails(self) -> None:
        path = self._memory_path(
            [self._valid_memory(evidence_snapshot_ids="not-a-list")]
        )
        result = verify_jsonl_export(path)
        assert not result.ok

    def test_empty_evidence_snapshot_ids_is_valid(self) -> None:
        """Empty evidence_snapshot_ids is allowed (newly created claim)."""
        path = self._memory_path([self._valid_memory(evidence_snapshot_ids=[])])
        result = verify_jsonl_export(path)
        assert result.ok
