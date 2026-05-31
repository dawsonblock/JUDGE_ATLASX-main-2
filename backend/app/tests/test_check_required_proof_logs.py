from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "check_required_proof_logs.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_required_proof_logs", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_strict_mode_prints_proof_incomplete_categories(
    tmp_path: Path, capsys
) -> None:
    module = _load_module()
    root = tmp_path / "repo"

    _write(
        root / "artifacts" / "proof" / "current" / "release_gate.json",
        json.dumps(
            {
                "checks": [
                    {
                        "name": "required_proof_logs",
                        "log_path": "artifacts/proof/current/required_proof_logs.log",
                    }
                ],
                "logs": {
                    "required_proof_logs": "artifacts/proof/current/required_proof_logs.log"
                },
            },
            indent=2,
        )
        + "\n",
    )

    old_argv = sys.argv
    try:
        sys.argv = [
            "prog",
            "--root",
            str(root),
            "--strict-required-files",
        ]
        rc = module.main()
    finally:
        sys.argv = old_argv

    stdout = capsys.readouterr().out
    assert rc == 1
    assert "REQUIRED_PROOF_LOGS: FAIL" in stdout
    assert "PROOF_INCOMPLETE:" in stdout
    assert "missing_referenced_logs=" in stdout
    assert "missing_required_proof_files=" in stdout
