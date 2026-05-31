from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "validate_release_archive.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_release_archive", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_zip(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)


def _valid_files(root: str = "JUDGE_ATLAS-main") -> dict[str, str]:
    prefix = f"{root}/"
    return {
        prefix + ".github/workflows/ci.yml": "name: ci\n",
        prefix + "backend/app/main.py": "print('ok')\n",
        prefix + "demo/README.md": "demo\n",
        prefix + "frontend/package.json": "{}\n",
        prefix + "infra/main.bicep": "resource x 'Microsoft.Resources/resourceGroups@2021-04-01' = {}\n",
        prefix + "docs/README.md": "docs\n",
        prefix + "scripts/release_gate.py": "print('gate')\n",
        prefix + "artifacts/proof/current/CURRENT_PROOF.md": "current proof\n",
        prefix + "artifacts/proof/current/CURRENT_ALPHA_STATUS.md": "alpha status\n",
        prefix + "artifacts/proof/current/REPAIR_REPORT.md": "repair report\n",
        prefix + "artifacts/proof/current/FIX_VERIFICATION_REPORT.md": "fixes\n",
        prefix + "artifacts/proof/current/SOURCE_REGISTRY_STATUS.md": "registry status\n",
        prefix + "artifacts/proof/current/proof_manifest.json": (
            "{\n"
            '  "required_logs": [\n'
            '    "artifacts/proof/current/release_gate.log"\n'
            "  ]\n"
            "}\n"
        ),
        prefix + "artifacts/proof/current/release_gate.json": (
            "{\n"
            '  "alpha_gate_passed": true,\n'
            '  "release_candidate": true,\n'
            '  "production_ready": false\n'
            "}\n"
        ),
        prefix + "artifacts/proof/current/release_gate.log": "gate log\n",
        prefix + "artifacts/proof/current/release_readiness.md": "current readiness\n",
        prefix + "artifacts/proof/current/required_log_index.json": "{}\n",
        prefix + "artifacts/proof/current/source_registry_status.json": "{}\n",
        prefix + "README.md": "repo readme\n",
        prefix + "STATUS.md": "Production ready: FALSE\n",
    }


def test_validate_release_archive_accepts_valid_archive(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "valid.zip"
    _write_zip(archive, _valid_files())

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is True
    assert report["top_level_roots"] == ["JUDGE_ATLAS-main"]


def test_validate_release_archive_allows_blocked_snapshot_with_warnings(
    tmp_path: Path,
) -> None:
    module = _load_module()
    archive = tmp_path / "blocked.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json"] = (
        "{\n"
        '  "alpha_gate_passed": false,\n'
        '  "release_candidate": false,\n'
        '  "production_ready": false\n'
        "}\n"
    )
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is True
    assert "release_gate_not_alpha_passed" in report["warnings"]
    assert "release_gate_not_release_candidate" in report["warnings"]
    assert "release_gate_not_alpha_passed" not in report["errors"]
    assert "release_gate_not_release_candidate" not in report["errors"]


def test_validate_release_archive_can_require_release_candidate(
    tmp_path: Path,
) -> None:
    module = _load_module()
    archive = tmp_path / "blocked-strict.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json"] = (
        "{\n"
        '  "alpha_gate_passed": false,\n'
        '  "release_candidate": false,\n'
        '  "production_ready": false\n'
        "}\n"
    )
    _write_zip(archive, files)

    report = module.inspect_archive(
        archive,
        expected_root="JUDGE_ATLAS-main",
        require_release_candidate=True,
    )

    assert report["valid"] is False
    assert "release_gate_not_alpha_passed" in report["errors"]
    assert "release_gate_not_release_candidate" in report["errors"]


def test_validate_release_archive_rejects_wrong_root(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "wrong-root.zip"
    _write_zip(archive, _valid_files(root="JUDGE-main"))

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert "archive_root_mismatch:JUDGE-main!=JUDGE_ATLAS-main" in report["errors"]


def test_validate_release_archive_rejects_node_modules(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "node-modules.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/frontend/node_modules/react/index.js"] = "module.exports = {}\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("forbidden_path:") for error in report["errors"])


def test_validate_release_archive_rejects_external_by_default(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "external.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/external/reference/README.md"] = "external ref\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("forbidden_external_path:") for error in report["errors"])


def test_validate_release_archive_rejects_missing_current_proof_dir(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "missing-proof.zip"
    files = _valid_files()
    files.pop("JUDGE_ATLAS-main/artifacts/proof/current/CURRENT_PROOF.md")
    files.pop("JUDGE_ATLAS-main/artifacts/proof/current/release_readiness.md")
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert "missing_required_directory:artifacts/proof/current/" in report["errors"] or any(
        error.startswith("missing_required_proof_file:") for error in report["errors"]
    )


def test_validate_release_archive_rejects_env_file(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "env.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/.env"] = "SECRET=1\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("forbidden_secret_file:") for error in report["errors"])


def test_validate_release_archive_rejects_research_path(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "research.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/research/crawlee-python-master/foo.py"] = "crawlee\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("forbidden_research_path:") for error in report["errors"])


def test_validate_release_archive_rejects_archive_validation_md(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "archive-val-md.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/archive_validation.md"] = "validation output\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(
        error.startswith("forbidden_secret_file:") and "archive_validation.md" in error
        for error in report["errors"]
    )


def test_validate_release_archive_rejects_archive_validation_log(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "archive-val-log.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/archive_validation.log"] = "log output\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(
        error.startswith("forbidden_secret_file:") and "archive_validation.log" in error
        for error in report["errors"]
    )


def test_validate_release_archive_rejects_trailing_whitespace_segment(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "whitespace-segment.zip"
    files = _valid_files()
    # "Research " (trailing space) is the canonical regression from the audit
    files["JUDGE_ATLAS-main/Research /crawlee-python-master/foo.py"] = "crawlee\n"
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("whitespace_path_segment:") for error in report["errors"])


def test_validate_release_archive_rejects_missing_claimed_check_log_path(
    tmp_path: Path,
) -> None:
    module = _load_module()
    archive = tmp_path / "missing-check-log.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json"] = (
        '{\n'
        '  "checks": [\n'
        '    {"name": "required_proof_logs", '
        '"log_path": "artifacts/proof/current/required_proof_logs.log"}\n'
        '  ]\n'
        '}\n'
    )
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(
        error.startswith("missing_claimed_proof_file:checks.required_proof_logs:")
        for error in report["errors"]
    )


def test_validate_release_archive_marks_proof_count_mismatch_as_error(
    tmp_path: Path,
) -> None:
    module = _load_module()
    archive = tmp_path / "count-mismatch.zip"
    files = _valid_files()
    files["JUDGE_ATLAS-main/artifacts/proof/current/release_gate.json"] = (
        '{\n'
        '  "check_count": 5,\n'
        '  "proof_input_file_count": 21\n'
        '}\n'
    )
    files["JUDGE_ATLAS-main/artifacts/proof/current/CURRENT_PROOF.md"] = (
        "# CURRENT_PROOF\n"
        "\n"
        "- unrelated_metric: 999\n"
    )
    _write_zip(archive, files)

    report = module.inspect_archive(archive, expected_root="JUDGE_ATLAS-main")

    assert report["valid"] is False
    assert any(error.startswith("proof_count_mismatch:") for error in report["errors"])


def test_validate_release_archive_main_prints_proof_incomplete_summary(
    tmp_path: Path, capsys
) -> None:
    module = _load_module()
    archive = tmp_path / "stdout-proof-incomplete.zip"
    files = _valid_files()
    files.pop("JUDGE_ATLAS-main/artifacts/proof/current/CURRENT_ALPHA_STATUS.md")
    _write_zip(archive, files)

    output_md = tmp_path / "archive_validation.md"
    old_argv = sys.argv
    try:
        sys.argv = [
            "prog",
            "--archive",
            str(archive),
            "--expected-root",
            "JUDGE_ATLAS-main",
            "--output",
            str(output_md),
        ]
        rc = module.main()
    finally:
        sys.argv = old_argv

    stdout = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in stdout
    assert "PROOF_INCOMPLETE:" in stdout
    assert "missing_required_proof_files=" in stdout
