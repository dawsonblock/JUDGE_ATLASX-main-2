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


def _seed_minimal_repo(root: Path) -> None:
    (root / "backend" / "app").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "alembic" / "versions").mkdir(parents=True, exist_ok=True)
    (root / "frontend").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "security").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "deployment-guide").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "demo").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "proof" / "history").mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text("repo\n", encoding="utf-8")
    (root / "CURRENT_STATUS.md").write_text("alpha\n", encoding="utf-8")
    (root / "PROOF_STATUS.md").write_text("proof\n", encoding="utf-8")
    (root / "RELEASE_BLOCKERS.md").write_text("none\n", encoding="utf-8")
    (root / "STUBS_AND_PLACEHOLDERS.md").write_text("stub\n", encoding="utf-8")
    (root / "REPO_REALITY.md").write_text("reality\n", encoding="utf-8")
    (root / "COMPLETION_CHECKLIST.md").write_text("alpha checklist\n", encoding="utf-8")
    (root / "Makefile").write_text("all:\n\t@echo ok\n", encoding="utf-8")
    (root / ".github" / "workflows" / "alpha.yml").write_text(
        "name: alpha\n", encoding="utf-8"
    )
    (root / "backend" / "app" / "sample.py").write_text("x = 1\n", encoding="utf-8")
    (root / "backend" / "alembic" / "versions" / "0001_init.py").write_text(
        "# migration\n", encoding="utf-8"
    )
    (root / "backend" / "pyproject.toml").write_text(
        "[project]\nname='x'\n", encoding="utf-8"
    )
    (root / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "scripts" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "demo" / "seed.json").write_text('{"demo": true}\n', encoding="utf-8")
    (root / "docs" / "CURRENT_STATUS.md").write_text("status\n", encoding="utf-8")
    (root / "docs" / "DB_PROOF.md").write_text("db\n", encoding="utf-8")
    (root / "docs" / "security" / "FRONTEND_SECURITY_TRIAGE.md").write_text(
        "triage\n", encoding="utf-8"
    )
    (root / "docs" / "schema_audit.md").write_text("audit\n", encoding="utf-8")
    (root / "docs" / "security" / "LEGACY_AUTH_REMOVAL_PLAN.md").write_text(
        "legacy\n", encoding="utf-8"
    )
    (root / "docs" / "deployment-guide" / "DEPENDENCY_REMEDIATION_PLAN.md").write_text(
        "deps\n", encoding="utf-8"
    )
    (root / "artifacts" / "proof" / "CURRENT_PROOF.md").write_text(
        "pointer\n", encoding="utf-8"
    )

def _write_release_gate(
    repo_root: Path,
    proof_hash: str,
    proof_input_file_list: list[str],
    *,
    include_current_proof_line: bool = True,
    proof_input_file_fingerprints: dict[str, dict[str, int | str]] | None = None,
) -> None:
    release_gate = {
        "proof_input_tree_hash": proof_hash,
        "proof_input_tree_hash_algorithm": "sha256",
        "proof_input_file_count": len(proof_input_file_list),
        "proof_input_file_list": proof_input_file_list,
        "proof_input_file_fingerprints": proof_input_file_fingerprints or {},
    }
    (repo_root / "artifacts" / "proof" / "current" / "release_gate.json").write_text(
        json.dumps(release_gate), encoding="utf-8"
    )
    proof_line = f"- proof_input_tree_hash: {proof_hash}\n" if include_current_proof_line else ""
    (repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md").write_text(
        proof_line,
        encoding="utf-8",
    )


def _proof_module():
    return _load_module(
        "check_proof_freshness_module",
        Path(__file__).resolve().parents[3] / "scripts" / "check_proof_freshness.py",
    )


def test_release_gate_writes_proof_input_file_list() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    release_gate = _load_module("release_gate_module_files", repo_root / "scripts" / "release_gate.py")
    metadata = release_gate._collect_proof_input_metadata(repo_root, sys.executable)
    assert isinstance(metadata["proof_input_file_list"], list)
    assert metadata["proof_input_file_list"]


def test_release_gate_writes_proof_input_tree_hash() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    release_gate = _load_module("release_gate_module_hash", repo_root / "scripts" / "release_gate.py")
    check_proof_freshness = _proof_module()
    metadata = release_gate._collect_proof_input_metadata(repo_root, sys.executable)
    expected_hash, _ = check_proof_freshness.compute_proof_input_tree_hash(repo_root)
    assert metadata["proof_input_tree_hash"] == expected_hash
    assert metadata["proof_input_tree_hash_algorithm"] == "sha256"


def test_release_gate_writes_proof_input_file_count() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    release_gate = _load_module("release_gate_module_count", repo_root / "scripts" / "release_gate.py")
    metadata = release_gate._collect_proof_input_metadata(repo_root, sys.executable)
    assert metadata["proof_input_file_count"] == len(metadata["proof_input_file_list"])


def test_release_gate_writes_proof_input_file_fingerprints() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    release_gate = _load_module("release_gate_module_fingerprints", repo_root / "scripts" / "release_gate.py")
    metadata = release_gate._collect_proof_input_metadata(repo_root, sys.executable)
    fingerprints = metadata["proof_input_file_fingerprints"]
    assert isinstance(fingerprints, dict)
    assert fingerprints
    first_key = next(iter(fingerprints))
    assert "sha256" in fingerprints[first_key]
    assert "size_bytes" in fingerprints[first_key]


def test_proof_freshness_passes_when_stored_file_list_matches(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "PASS"


def test_proof_freshness_fails_when_listed_file_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    metadata = module.metadata_payload(repo_root)
    _write_release_gate(
        repo_root,
        metadata["proof_input_tree_hash"],
        metadata["proof_input_file_list"],
        proof_input_file_fingerprints=metadata["proof_input_file_fingerprints"],
    )
    (repo_root / "backend" / "app" / "sample.py").write_text("x = 2\n", encoding="utf-8")
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"
    assert "hash mismatch" in result["message"]
    assert "backend/app/sample.py" in result["changed_files"]


def test_proof_freshness_fails_when_listed_file_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "scripts" / "helper.py").unlink()
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"
    assert result["missing_files"]


def test_proof_freshness_detects_demo_file_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "demo" / "seed.json").write_text('{"demo": false}\n', encoding="utf-8")
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"


def test_proof_freshness_detects_github_workflow_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / ".github" / "workflows" / "alpha.yml").write_text(
        "name: changed\n", encoding="utf-8"
    )
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"


def test_proof_freshness_detects_legacy_auth_plan_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "docs" / "security" / "LEGACY_AUTH_REMOVAL_PLAN.md").write_text(
        "legacy changed\n", encoding="utf-8"
    )
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"


def test_proof_freshness_detects_dependency_remediation_plan_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "docs" / "deployment-guide" / "DEPENDENCY_REMEDIATION_PLAN.md").write_text(
        "deps changed\n", encoding="utf-8"
    )
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"


def test_proof_freshness_ignores_current_proof_outputs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    before_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    (repo_root / "artifacts" / "proof" / "current" / "runtime.log").write_text(
        "runtime\n", encoding="utf-8"
    )
    after_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    assert before_hash == after_hash


def test_proof_freshness_ignores_history_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    before_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    (repo_root / "artifacts" / "proof" / "history" / "old.json").write_text(
        "old\n", encoding="utf-8"
    )
    after_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    assert before_hash == after_hash


def test_proof_freshness_ignores_pyc_and_cache_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    before_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    pycache_dir = repo_root / "backend" / "app" / "__pycache__"
    pycache_dir.mkdir(parents=True, exist_ok=True)
    (pycache_dir / "sample.cpython-311.pyc").write_bytes(b"pyc")
    after_hash, _ = module.compute_proof_input_tree_hash(repo_root)
    assert before_hash == after_hash


def test_proof_freshness_is_independent_of_git_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    assert not (repo_root / ".git").exists()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "PASS"


def test_proof_freshness_strict_extra_files_fails_on_new_proof_input(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "scripts" / "new_script.py").write_text("print('new')\n", encoding="utf-8")
    result = module.validate_stored_manifest(repo_root, strict_extra_files=True)
    assert result["status"] == "FAIL"
    assert result["extra_files"]


def test_proof_freshness_default_warns_on_new_proof_input(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "scripts" / "new_script.py").write_text("print('new')\n", encoding="utf-8")
    result = module.validate_stored_manifest(repo_root, strict_extra_files=False)
    assert result["status"] == "PASS"
    assert result["extra_files"]
    assert "new proof-relevant files" in result["message"]


def test_proof_freshness_detects_completion_checklist_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _seed_minimal_repo(repo_root)
    module = _proof_module()
    proof_hash, files = module.compute_proof_input_tree_hash(repo_root)
    _write_release_gate(repo_root, proof_hash, files)
    (repo_root / "COMPLETION_CHECKLIST.md").write_text("alpha checklist changed\n", encoding="utf-8")
    result = module.validate_stored_manifest(repo_root)
    assert result["status"] == "FAIL"
    assert "hash mismatch" in result["message"]
