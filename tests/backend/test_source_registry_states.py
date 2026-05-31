from pathlib import Path


def test_source_registry_state_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_source_registry_contracts.py",
        root / "backend/app/tests/test_source_registry_control_plane.py",
        root / "backend/app/tests/test_source_registry_consistency.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required source-state tests: {missing}"
