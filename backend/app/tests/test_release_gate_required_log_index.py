from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "release_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_gate"] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_write_required_log_index_tracks_required_logs(tmp_path: Path) -> None:
    module = _load_module()
    repo_root = tmp_path / "repo"
    out_dir = repo_root / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)

    _write(out_dir / "release_gate.log", "ok\n")
    _write(out_dir / "docker_smoke.log", "ok\n")

    manifest = {
        "generated_at": "2026-05-25T00:00:00Z",
        "proof_root": "artifacts/proof/current",
        "required_logs": [
            "artifacts/proof/current/release_gate.log",
            "artifacts/proof/current/docker_smoke.log",
        ],
        "proof_commands": [
            {
                "name": "release_gate",
                "path": "artifacts/proof/current/release_gate.log",
                "sha256": module._sha256_file(out_dir / "release_gate.log"),
                "size_bytes": (out_dir / "release_gate.log").stat().st_size,
            },
            {
                "name": "docker_smoke",
                "path": "artifacts/proof/current/docker_smoke.log",
                "sha256": module._sha256_file(out_dir / "docker_smoke.log"),
                "size_bytes": (out_dir / "docker_smoke.log").stat().st_size,
            },
        ],
    }

    rel_path = module._write_required_log_index(repo_root, out_dir, manifest)
    assert rel_path == "artifacts/proof/current/required_log_index.json"

    payload = json.loads((out_dir / "required_log_index.json").read_text(encoding="utf-8"))
    assert payload["required_logs_total"] == 2
    assert payload["missing_required_logs"] == []
    for entry in payload["entries"]:
        assert entry["status"] == "PASS"
        assert entry["location_scope"] == "archive_internal"
