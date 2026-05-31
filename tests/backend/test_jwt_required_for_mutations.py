from pathlib import Path


def test_jwt_required_for_mutations_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_jwt_mutation_enforcement.py",
        root / "backend/app/tests/test_jwt_mutation_enforcement_default.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required jwt mutation tests: {missing}"
