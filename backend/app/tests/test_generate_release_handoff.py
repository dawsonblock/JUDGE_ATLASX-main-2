from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "generate_release_handoff.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_release_handoff", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_repo(root: Path) -> Path:
    archive_path = root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b"archive-bytes")

    _write_file(root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md", "proof\n")
    _write_file(root / "artifacts" / "proof" / "current" / "CURRENT_ALPHA_STATUS.md", "alpha\n")
    _write_file(root / "artifacts" / "proof" / "current" / "SOURCE_REGISTRY_STATUS.md", "registry\n")
    _write_file(root / "artifacts" / "proof" / "current" / "source_registry_status.json", "{}\n")
    _write_file(root / "artifacts" / "proof" / "current" / "proof_manifest.json", "{}\n")
    _write_file(root / "artifacts" / "proof" / "current" / "required_log_index.json", "{}\n")
    _write_file(root / "artifacts" / "proof" / "current" / "REPAIR_REPORT.md", "repair\n")
    _write_file(root / "artifacts" / "proof" / "current" / "FIX_VERIFICATION_REPORT.md", "fix\n")
    _write_file(root / "artifacts" / "proof" / "current" / "release_readiness.md", "ready\n")
    _write_file(root / "artifacts" / "proof" / "current" / "PROOF_POLICY.md", "policy\n")
    _write_file(root / "artifacts" / "proof" / "current" / "proof_freshness.log", "ok\n")

    _write_file(
        root / "artifacts" / "proof" / "current" / "release_gate.json",
        json.dumps(
            {
                "alpha_gate_passed": True,
                "release_candidate": True,
                "production_ready": False,
                "checks": [
                    {
                        "name": "proof_freshness",
                        "log_path": "artifacts/proof/current/proof_freshness.log",
                    }
                ],
                "logs": {
                    "proof_freshness": "artifacts/proof/current/proof_freshness.log"
                },
                "runtime": {"python": "3.11.7", "node_version": "v20.20.2", "npm_version": "10.8.2"},
            },
            indent=2,
        )
        + "\n",
    )
    return archive_path


def test_generate_release_handoff_fails_when_referenced_log_missing(tmp_path: Path) -> None:
    module = _load_module()
    repo_root = tmp_path / "repo"
    archive_path = _seed_repo(repo_root)

    (repo_root / "artifacts" / "proof" / "current" / "proof_freshness.log").unlink()

    old_argv = sys.argv
    try:
        sys.argv = [
            "prog",
            "--root",
            str(repo_root),
            "--archive",
            str(archive_path),
            "--output",
            "FINAL_RELEASE_HANDOFF.md",
        ]
        try:
            module.main()
        except SystemExit as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected generate_release_handoff to fail when referenced proof log is missing")
    finally:
        sys.argv = old_argv

    assert "PROOF_INCOMPLETE:" in message
    assert "missing_referenced_logs=artifacts/proof/current/proof_freshness.log" in message


def test_generate_release_handoff_writes_proof_complete_status(tmp_path: Path) -> None:
    module = _load_module()
    repo_root = tmp_path / "repo"
    archive_path = _seed_repo(repo_root)

    output_path = repo_root / "FINAL_RELEASE_HANDOFF.md"

    old_argv = sys.argv
    try:
        sys.argv = [
            "prog",
            "--root",
            str(repo_root),
            "--archive",
            str(archive_path),
            "--output",
            str(output_path),
        ]
        ret = module.main()
    finally:
        sys.argv = old_argv

    assert ret == 0
    contents = output_path.read_text(encoding="utf-8")
    assert "- proof_complete: true" in contents
    assert "- release_classification: proof-hardened alpha release candidate" in contents
    assert "- This is a proof-hardened alpha release candidate." in contents
    assert "- It is not ready for production deployment." in contents
