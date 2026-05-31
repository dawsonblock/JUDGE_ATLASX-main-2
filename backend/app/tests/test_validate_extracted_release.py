from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "validate_extracted_release.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_extracted_release", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_checks_includes_strict_required_proof_logs() -> None:
    module = _load_module()
    checks = module._build_checks(
        runtime_root=Path("/tmp/runtime"),
        repo_root=Path("/tmp/repo"),
        archive_path=Path("/tmp/repo/dist/final.zip"),
        expected_root="JUDGE_ATLAS-main",
    )

    target = next(name for name, _cmd, _cwd in checks if name == "check_required_proof_logs")
    assert target == "check_required_proof_logs"

    command = next(cmd for name, cmd, _cwd in checks if name == "check_required_proof_logs")
    assert "--strict-required-files" in command


def test_build_checks_includes_verify_proof_hash_sync() -> None:
    module = _load_module()
    checks = module._build_checks(
        runtime_root=Path("/tmp/runtime"),
        repo_root=Path("/tmp/repo"),
        archive_path=Path("/tmp/repo/dist/final.zip"),
        expected_root="JUDGE_ATLAS-main",
    )

    names = [name for name, _cmd, _cwd in checks]
    assert "verify_proof_hash_sync" in names

    verify_index = names.index("verify_proof_hash_sync")
    freshness_index = names.index("check_proof_freshness")
    assert verify_index > freshness_index


def test_main_reports_failed_check_names(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_module()

    archive_path = tmp_path / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("JUDGE_ATLAS-main/scripts/release_gate.py", "print('ok')\n")
        zf.writestr("JUDGE_ATLAS-main/scripts/.keep", "\n")
        zf.writestr("JUDGE_ATLAS-main/backend/.keep", "\n")
        zf.writestr("JUDGE_ATLAS-main/frontend/.keep", "\n")

    def fake_run(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
        joined = " ".join(cmd)
        if "check_required_proof_logs.py" in joined:
            return 1, "missing required proof logs"
        return 0, ""

    monkeypatch.setattr(module, "_run", fake_run)

    old_argv = sys.argv
    try:
        sys.argv = [
            "prog",
            "--root",
            str(tmp_path),
            "--archive",
            str(archive_path),
            "--expected-root",
            "JUDGE_ATLAS-main",
        ]
        rc = module.main()
    finally:
        sys.argv = old_argv

    out = capsys.readouterr().out
    assert rc == 1
    assert "EXTRACTED_RELEASE_VALIDATION: FAIL" in out
    assert "- check_required_proof_logs: rc=1" in out
    assert "missing required proof logs" in out
