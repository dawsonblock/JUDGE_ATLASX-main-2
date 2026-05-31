import sys
from importlib import util
from pathlib import Path


def _load_release_gate_module():
    module_path = Path(__file__).resolve().parents[3] / "scripts" / "release_gate.py"
    spec = util.spec_from_file_location("release_gate_module", module_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_proof_manifest_includes_required_metadata(tmp_path):
    module = _load_release_gate_module()
    repo_root = tmp_path
    out_dir = tmp_path / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True)
    log_path = repo_root / "artifacts" / "proof" / "current" / "sample.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("sample proof log\n", encoding="utf-8")

    payload = {
        "timestamp_utc": "2026-05-25T00:00:00Z",
        "commit_hash": "abc123",
        "platform": "darwin",
        "python_version": "3.11.0",
        "node_version": "20.0.0",
        "frontend_node_gate_version": "20.0.0",
        "npm_version": "10.0.0",
        "proof_input_tree_hash": "deadbeef",
        "proof_input_file_count": 1,
    }
    step = module.GateStep(
        name="sample_check",
        command="python -m pytest",
        status="PASS",
        exit_code=0,
        duration_seconds=0.5,
        log_path="artifacts/proof/current/sample.log",
        started_at_utc="2026-05-25T00:00:00Z",
        finished_at_utc="2026-05-25T00:00:01Z",
        required=True,
        cwd=str(repo_root),
        failure_reason=None,
    )

    manifest = module._build_proof_manifest(repo_root, out_dir, payload, [step])
    entry = manifest["proof_commands"][0]

    assert entry["path"] == "artifacts/proof/current/sample.log"
    assert entry["sha256"] == entry["log_sha256"]
    assert entry["size_bytes"] == log_path.stat().st_size
    assert entry["captured_at"] == "2026-05-25T00:00:01Z"
    assert entry["created_at"] == "2026-05-25T00:00:01Z"
    assert entry["command"] == "python -m pytest"
    assert entry["required"] is True


def test_build_proof_manifest_includes_supplemental_log_artifacts(tmp_path):
    module = _load_release_gate_module()
    repo_root = tmp_path
    out_dir = tmp_path / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True)
    release_gate_log = out_dir / "release_gate.log"
    release_gate_log.write_text("gate log\n", encoding="utf-8")

    payload = {
        "timestamp_utc": "2026-05-25T00:00:00Z",
        "logs": {
            "release_gate": "artifacts/proof/current/release_gate.log",
            "current_proof": "artifacts/proof/current/CURRENT_PROOF.md",
        },
    }

    manifest = module._build_proof_manifest(repo_root, out_dir, payload, [])
    entry_map = {entry["path"]: entry for entry in manifest["proof_commands"]}

    assert "artifacts/proof/current/release_gate.log" in entry_map
    assert "artifacts/proof/current/CURRENT_PROOF.md" not in entry_map
    assert entry_map["artifacts/proof/current/release_gate.log"]["proof_source"] == "release_gate"


def test_run_backfills_empty_success_logs(tmp_path):
    module = _load_release_gate_module()
    repo_root = tmp_path
    out_dir = tmp_path / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True)

    step = module._run(
        repo_root,
        out_dir,
        "quiet_step",
        "quiet_step.log",
        [sys.executable, "-c", ""],
    )

    log_path = repo_root / step.log_path
    assert step.exit_code == 0
    assert log_path.read_text(encoding="utf-8").strip()