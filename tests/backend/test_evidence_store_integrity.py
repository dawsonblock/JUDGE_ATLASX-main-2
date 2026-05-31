from pathlib import Path


def test_evidence_store_integrity_checks_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "scripts/verify_evidence_store.py",
        root / "scripts/verify_snapshot_hashes.py",
        root / "backend/app/tests/test_snapshot_integrity.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required evidence integrity checks: {missing}"
