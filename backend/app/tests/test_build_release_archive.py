from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_release_archive.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_release_archive", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_repo(root: Path) -> None:
    _write_file(root / "README.md", "readme\n")
    _write_file(root / "STATUS.md", "Production ready: FALSE\n")
    _write_file(root / "backend" / "app" / "main.py", "print('ok')\n")
    _write_file(root / "frontend" / "package.json", "{}\n")
    _write_file(root / "docs" / "README.md", "docs\n")
    _write_file(root / "scripts" / "release_gate.py", "print('gate')\n")
    _write_file(root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md", "proof\n")
    _write_file(root / "artifacts" / "proof" / "current" / "CURRENT_ALPHA_STATUS.md", "alpha\n")
    _write_file(root / "artifacts" / "proof" / "current" / "SOURCE_REGISTRY_STATUS.md", "registry\n")
    _write_file(root / "artifacts" / "proof" / "current" / "source_registry_status.json", "{}\n")
    _write_file(root / "artifacts" / "proof" / "current" / "release_gate.json", json.dumps({"logs": {}}, indent=2) + "\n")
    _write_file(
        root / "artifacts" / "proof" / "current" / "proof_manifest.json",
        json.dumps({"required_logs": [], "proof_commands": []}, indent=2)
        + "\n",
    )
    _write_file(
        root / "artifacts" / "proof" / "current" / "required_log_index.json",
        json.dumps({"entries": []}, indent=2) + "\n",
    )
    _write_file(root / "artifacts" / "proof" / "current" / "REPAIR_REPORT.md", "repair report\n")
    _write_file(root / "artifacts" / "proof" / "current" / "FIX_VERIFICATION_REPORT.md", "fixes\n")
    _write_file(root / "artifacts" / "proof" / "current" / "release_readiness.md", "ready\n")
    _write_file(root / "artifacts" / "proof" / "current" / "PROOF_POLICY.md", "policy\n")
    _write_file(root / "external" / "reference" / "README.md", "external\n")
    _write_file(root / "artifacts" / "proof" / "archive" / "old.txt", "old\n")


def test_build_release_archive_excludes_external_and_proof_archive_by_default(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "clean.zip"
    result = module.build_archive(
        output=output,
        root_name="JUDGE_ATLAS-main",
        include_external=False,
        include_proof_archive=False,
        allow_noncanonical=True,
    )

    assert output.exists()
    assert len(result["archive_sha256"]) == 64

    with zipfile.ZipFile(output, "r") as zf:
        names = set(zf.namelist())
        assert "JUDGE_ATLAS-main/RELEASE_MANIFEST.json" in names
        assert "JUDGE_ATLAS-main/artifacts/proof/current/CURRENT_PROOF.md" in names
        assert all("/external/" not in name for name in names)
        assert all("/artifacts/proof/archive/" not in name for name in names)

        manifest = json.loads(zf.read("JUDGE_ATLAS-main/RELEASE_MANIFEST.json").decode("utf-8"))
        assert manifest["production_ready"] is False
        assert manifest["proof_path"] == "artifacts/proof/current"
        assert isinstance(manifest["archive_sha256"], str)
        assert len(manifest["archive_sha256"]) == 64


def test_dry_run_does_not_write_zip(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "dry.zip"
    old_argv = sys.argv
    try:
        sys.argv = ["prog", "--dry-run", "--output", str(output)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = module.main()
    finally:
        sys.argv = old_argv

    assert ret == 0
    assert not output.exists(), "dry-run must not write the zip file"


def test_dry_run_reports_invalid_when_referenced_log_missing(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    _write_file(
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
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "dry.zip"
    old_argv = sys.argv
    try:
        sys.argv = ["prog", "--dry-run", "--json", "--output", str(output)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = module.main()
    finally:
        sys.argv = old_argv

    payload = json.loads(buf.getvalue())
    assert ret == 0
    assert payload["dry_run"] is True
    assert payload["dry_run_valid"] is False
    assert "artifacts/proof/current/required_proof_logs.log" in payload["missing_referenced_proof_files"]
    assert not output.exists(), "dry-run must not write the zip file"


def test_strict_dry_run_fails_on_missing_referenced_log(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    _write_file(
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
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "dry.zip"
    old_argv = sys.argv
    try:
        sys.argv = ["prog", "--dry-run", "--strict-dry-run", "--output", str(output)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = module.main()
    finally:
        sys.argv = old_argv

    assert ret == 1
    assert "required_proof_logs.log" in buf.getvalue()
    assert not output.exists(), "strict dry-run must not write the zip file"


def test_archive_validation_files_excluded(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    _write_file(
        root / "artifacts" / "proof" / "current" / "release_gate.json",
        json.dumps(
            {
                "logs": {
                    "archive_validation": "artifacts/proof/current/archive_validation.log",
                },
                "checks": [
                    {
                        "name": "archive_validation",
                        "log_path": "artifacts/proof/current/archive_validation.log",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
    )
    _write_file(
        root / "artifacts" / "proof" / "current" / "proof_manifest.json",
        json.dumps(
            {
                "proof_commands": [
                    {
                        "name": "archive_validation",
                        "path": "artifacts/proof/current/archive_validation.log",
                        "log_path": "artifacts/proof/current/archive_validation.log",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
    )
    _write_file(root / "artifacts" / "proof" / "current" / "archive_validation.md", "val output\n")
    _write_file(root / "artifacts" / "proof" / "current" / "archive_validation.log", "log output\n")
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "clean.zip"
    module.build_archive(
        output=output,
        root_name="JUDGE_ATLAS-main",
        include_external=False,
        include_proof_archive=False,
        allow_noncanonical=True,
    )

    with zipfile.ZipFile(output, "r") as zf:
        names = set(zf.namelist())
        assert not any("archive_validation.md" in n for n in names)
        assert "JUDGE_ATLAS-main/artifacts/proof/current/archive_validation.log" not in names

        release_gate = json.loads(
            zf.read("JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json").decode("utf-8")
        )
        assert "archive_validation" not in release_gate.get("logs", {})
        assert not any(
            entry.get("name") == "archive_validation"
            for entry in release_gate.get("checks", [])
            if isinstance(entry, dict)
        )

        proof_manifest = json.loads(
            zf.read("JUDGE_ATLAS-main/artifacts/proof/current/proof_manifest.json").decode("utf-8")
        )
        assert not any(
            entry.get("name") == "archive_validation"
            for entry in proof_manifest.get("proof_commands", [])
            if isinstance(entry, dict)
        )


def test_build_release_archive_fails_on_missing_release_gate_referenced_log(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _seed_repo(root)
    _write_file(
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
    module.REPO_ROOT = root

    output = tmp_path / "dist" / "clean.zip"
    try:
        module.build_archive(
            output=output,
            root_name="JUDGE_ATLAS-main",
            include_external=False,
            include_proof_archive=False,
            allow_noncanonical=True,
        )
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected build_archive to fail when referenced proof log is missing")

    assert "Missing packaged proof files required by release metadata" in message
    assert "artifacts/proof/current/required_proof_logs.log" in message
