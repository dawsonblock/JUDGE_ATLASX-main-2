import sys
from importlib import util
from pathlib import Path
import json


def _load_check_required_module():
    module_path = Path(__file__).resolve().parents[3] / "scripts" / "check_required_proof_logs.py"
    spec = util.spec_from_file_location("check_required_proof_logs_module", module_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_required_log_integrity_detects_hash_and_size_mismatch(tmp_path):
    module = _load_check_required_module()
    repo_root = tmp_path
    log_path = repo_root / "artifacts" / "proof" / "current" / "sample.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("sample proof log\n", encoding="utf-8")

    gate_payload = {
        "checks": [
            {
                "name": "sample_check",
                "log_path": "artifacts/proof/current/sample.log",
            }
        ],
        "logs": {
            "sample_check": "artifacts/proof/current/sample.log",
        },
    }
    manifest = {
        "required_logs": ["artifacts/proof/current/sample.log"],
        "proof_commands": [
            {
                "path": "artifacts/proof/current/sample.log",
                "size_bytes": 999,
                "sha256": "0" * 64,
                "required": True,
                "command": "python -m pytest",
                "captured_at": "2026-05-25T00:00:01Z",
            }
        ],
    }

    gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    manifest_path = repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    gate_path.write_text(json.dumps(gate_payload), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    missing, referenced_total, present_total = module.check_required_proof_logs(repo_root)

    assert "artifacts/proof/current/sample.log" in missing
    assert referenced_total == 1
    assert present_total == 0


def test_required_log_integrity_ignores_non_log_payload_artifacts(tmp_path):
    module = _load_check_required_module()
    repo_root = tmp_path
    proof_dir = repo_root / "artifacts" / "proof" / "current"
    proof_dir.mkdir(parents=True, exist_ok=True)

    log_path = proof_dir / "sample.log"
    log_path.write_text("sample proof log\n", encoding="utf-8")
    current_proof_path = proof_dir / "CURRENT_PROOF.md"
    current_proof_path.write_text("derived summary\n", encoding="utf-8")

    gate_payload = {
        "checks": [
            {
                "name": "sample_check",
                "log_path": "artifacts/proof/current/sample.log",
            }
        ],
        "logs": {
            "sample_check": "artifacts/proof/current/sample.log",
            "current_proof": "artifacts/proof/current/CURRENT_PROOF.md",
        },
    }
    manifest = {
        "required_logs": ["artifacts/proof/current/sample.log"],
        "proof_commands": [
            {
                "path": "artifacts/proof/current/sample.log",
                "size_bytes": log_path.stat().st_size,
                "sha256": module._sha256_path(log_path),
                "required": True,
                "command": "python -m pytest",
                "captured_at": "2026-05-25T00:00:01Z",
            }
        ],
    }

    gate_path = proof_dir / "release_gate.json"
    manifest_path = proof_dir / "proof_manifest.json"
    gate_path.write_text(json.dumps(gate_payload), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    missing, referenced_total, present_total = module.check_required_proof_logs(repo_root)

    assert missing == []
    assert referenced_total == 1
    assert present_total == 1


def test_missing_required_logs_omits_archive_validation_for_packaged_archives(
    tmp_path,
):
    module = _load_check_required_module()
    repo_root = tmp_path
    proof_dir = repo_root / "artifacts" / "proof" / "current"
    proof_dir.mkdir(parents=True, exist_ok=True)

    missing_default = module._missing_required_proof_logs(repo_root)
    missing_packaged = module._missing_required_proof_logs(
        repo_root,
        packaged_archive=True,
    )

    assert "artifacts/proof/current/archive_validation.log" in missing_default
    assert "artifacts/proof/current/archive_validation.log" not in missing_packaged