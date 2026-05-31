#!/usr/bin/env python3
"""Run real frontend/backend API contract validation.

This checker enforces:
- contract fixtures must exist and contain non-placeholder schema content
- frontend contract suite must pass (vitest)
- backend contract suite must pass (pytest test_api_contract_*.py)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = REPO_ROOT / "artifacts" / "contracts"
BACKEND_VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
BACKEND_PYTHON = str(BACKEND_VENV_PYTHON) if BACKEND_VENV_PYTHON.exists() else sys.executable
EXPECTED = [
    "public_map_markers.json",
    "public_entity_detail.json",
    "source_registry.json",
    "review_queue_item.json",
    "evidence_snapshot.json",
    "ai_review_result.json",
    "error_response.json",
]

# Minimum keys that every top-level JSON Schema object must contain.
_REQUIRED_SCHEMA_KEYS = {"$schema", "required", "type"}
# At least one of these must be present to describe the shape.
_SHAPE_KEYS = {"properties", "items"}
_MIN_CONTRACT_BYTES = 160


def _run(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def _validate_schema(data: dict) -> list[str]:
    """Return a list of structural violations for *data*."""
    errors: list[str] = []
    missing_top = _REQUIRED_SCHEMA_KEYS - data.keys()
    if missing_top:
        errors.append(f"missing top-level schema keys: {sorted(missing_top)}")
    if not (_SHAPE_KEYS & data.keys()):
        errors.append(f"schema must have at least one of {sorted(_SHAPE_KEYS)}")
    return errors


def main() -> int:
    missing: list[str] = []
    invalid: list[str] = []
    schema_errors: list[str] = []
    tiny_contracts: list[str] = []

    for name in EXPECTED:
        path = CONTRACT_DIR / name
        if not path.exists():
            missing.append(name)
            continue
        if path.stat().st_size < _MIN_CONTRACT_BYTES:
            tiny_contracts.append(f"{name}: file too small ({path.stat().st_size} bytes)")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            invalid.append(f"{name}: {exc}")
            continue

        if not isinstance(data, dict):
            schema_errors.append(f"{name}: top-level value must be a JSON object")
            continue

        violations = _validate_schema(data)
        for v in violations:
            schema_errors.append(f"{name}: {v}")

    backend_contract_glob = sorted((REPO_ROOT / "backend" / "app" / "tests").glob("test_api_contract_*.py"))
    if not backend_contract_glob:
        missing.append("backend/app/tests/test_api_contract_*.py")

    frontend_rc, frontend_out = _run(["npm", "run", "test:contracts"], REPO_ROOT / "frontend")
    backend_command = [BACKEND_PYTHON, "-m", "pytest", "-q"] + [str(p) for p in backend_contract_glob]
    backend_rc, backend_out = _run(backend_command, REPO_ROOT)

    if missing or invalid or schema_errors or tiny_contracts or frontend_rc != 0 or backend_rc != 0:
        print("API CONTRACTS: FAIL")
        for name in missing:
            print(f"  missing:{name}")
        for item in invalid:
            print(f"  invalid:{item}")
        for item in schema_errors:
            print(f"  schema:{item}")
        for item in tiny_contracts:
            print(f"  tiny:{item}")
        if frontend_rc != 0:
            print("  frontend_contracts:FAIL")
            print(frontend_out)
        if backend_rc != 0:
            print("  backend_contracts:FAIL")
            print(backend_out)
        return 1

    print("API CONTRACTS: PASS")
    print(f"contracts_checked={len(EXPECTED)}")
    print("frontend_contracts=PASS")
    print("backend_contracts=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
