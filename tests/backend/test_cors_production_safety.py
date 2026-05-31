from pathlib import Path


def test_cors_production_safety_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    main_py = root / "backend/app/main.py"
    assert main_py.exists(), "missing backend/app/main.py"
    text = main_py.read_text(encoding="utf-8", errors="ignore")
    assert "_validate_cors_origins" in text
    assert "https://" in text
    assert "Wildcard '*' not allowed" in text
