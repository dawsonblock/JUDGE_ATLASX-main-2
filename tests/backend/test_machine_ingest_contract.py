from pathlib import Path


def test_machine_ingest_contract_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_ingestion_result_gate.py",
        root / "backend/app/tests/test_ingestion_source_gate.py",
        root / "backend/app/tests/test_source_registry_contracts.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required contract tests: {missing}"
