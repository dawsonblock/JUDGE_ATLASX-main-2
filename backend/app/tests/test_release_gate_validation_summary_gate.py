from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _release_gate_module():
    repo_root = Path(__file__).resolve().parents[3]
    return _load_module(
        "release_gate_validation_module",
        repo_root / "scripts" / "release_gate.py",
    )


def test_validation_summary_gate_missing_file(tmp_path: Path) -> None:
    module = _release_gate_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    result = module._validation_summary_gate(repo_root)

    assert result["status"] == "missing"
    assert result["exists"] is False
    assert result["blockers"] == []


def test_validation_summary_gate_failed_summary_blocks(tmp_path: Path) -> None:
    module = _release_gate_module()
    repo_root = tmp_path / "repo"
    summary_path = repo_root / ".validation_logs" / "validation_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "overall_status": "failed",
                "phases": {
                    "runtime_smoke": "failed",
                    "docker_smoke": "failed",
                    "preflight": "passed",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = module._validation_summary_gate(repo_root)

    assert result["status"] == "failed"
    assert result["exists"] is True
    assert result["failed_phases"] == ["docker_smoke", "runtime_smoke"]
    assert result["blockers"] == [
        "validation_summary_failed:docker_smoke,runtime_smoke"
    ]


def test_validation_summary_gate_passed_summary_no_blockers(tmp_path: Path) -> None:
    module = _release_gate_module()
    repo_root = tmp_path / "repo"
    summary_path = repo_root / ".validation_logs" / "validation_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "overall_status": "passed",
                "phases": {
                    "runtime_smoke": "passed",
                    "docker_smoke": "passed",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = module._validation_summary_gate(repo_root)

    assert result["status"] == "passed"
    assert result["exists"] is True
    assert result["failed_phases"] == []
    assert result["blockers"] == []
