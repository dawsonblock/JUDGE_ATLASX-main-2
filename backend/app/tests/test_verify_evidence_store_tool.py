from __future__ import annotations

from types import SimpleNamespace

import tools.verify_evidence_store as verifier  # type: ignore[import-not-found]


class _ScalarResult:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def all(self):
        return self._snapshots


class _FakeSession:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def scalars(self, _query):
        return _ScalarResult(self._snapshots)


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_verify_evidence_store_main_pass(monkeypatch, capsys):
    snapshots = [
        SimpleNamespace(content_hash="a" * 64),
        SimpleNamespace(content_hash="b" * 64),
    ]
    results = [SimpleNamespace(ok=True)]

    monkeypatch.setattr(
        verifier,
        "SessionLocal",
        lambda: _FakeSessionContext(_FakeSession(snapshots)),
    )
    monkeypatch.setattr(
        verifier,
        "verify_all_recent_snapshots",
        lambda db, limit: results,
    )

    assert verifier.main() == 0
    out = capsys.readouterr().out
    assert "EVIDENCE STORE VERIFICATION" in out
    assert "integrity_failures=0" in out
    assert "duplicate_hashes=0" in out
    assert "RESULT: PASS" in out


def test_verify_evidence_store_main_fails_on_integrity_mismatch(
    monkeypatch,
    capsys,
):
    snapshots = [SimpleNamespace(content_hash="a" * 64)]
    results = [
        SimpleNamespace(
            ok=False,
            snapshot_id=42,
            error_message="hash mismatch",
        ),
    ]

    monkeypatch.setattr(
        verifier,
        "SessionLocal",
        lambda: _FakeSessionContext(_FakeSession(snapshots)),
    )
    monkeypatch.setattr(
        verifier,
        "verify_all_recent_snapshots",
        lambda db, limit: results,
    )

    assert verifier.main() == 1
    out = capsys.readouterr().out
    assert "integrity_failures=1" in out
    assert "Integrity mismatches:" in out
    assert "snapshot_id=42" in out


def test_verify_evidence_store_main_fails_on_duplicate_hashes(
    monkeypatch,
    capsys,
):
    same_hash = "a" * 64
    snapshots = [
        SimpleNamespace(content_hash=same_hash),
        SimpleNamespace(content_hash=same_hash),
    ]
    results = [SimpleNamespace(ok=True), SimpleNamespace(ok=True)]

    monkeypatch.setattr(
        verifier,
        "SessionLocal",
        lambda: _FakeSessionContext(_FakeSession(snapshots)),
    )
    monkeypatch.setattr(
        verifier,
        "verify_all_recent_snapshots",
        lambda db, limit: results,
    )

    assert verifier.main() == 1
    out = capsys.readouterr().out
    assert "duplicate_hashes=1" in out
    assert "Duplicate content_hash entries:" in out
    assert "count=2" in out
