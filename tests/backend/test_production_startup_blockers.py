from pathlib import Path


def test_production_startup_blockers_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_production_preflight.py",
        root / "backend/app/tests/test_production_fetch_egress_policy.py",
        root / "backend/app/main.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required production startup blocker checks: {missing}"
