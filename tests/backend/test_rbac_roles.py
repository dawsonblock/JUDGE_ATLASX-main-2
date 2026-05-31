from pathlib import Path


def test_rbac_roles_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_mutation_rbac_matrix.py",
        root / "backend/app/tests/test_rbac_role_vocabulary.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required rbac role tests: {missing}"
