from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "check_release_naming_drift.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_release_naming_drift", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checker_rejects_clean_zip_reference(monkeypatch, tmp_path: Path, capsys) -> None:
    module = _load_module()

    repo_root = tmp_path / "repo"
    target = repo_root / "docs" / "release" / "example.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "Use dist/JUDGE_ATLASX-main.clean.zip for release\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(module, "SCAN_GLOBS", ("docs/**/*.md",))

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "RELEASE_NAMING_DRIFT: FAIL" in out
    assert "forbidden_release_archive_reference:" in out


def test_checker_passes_without_forbidden_references(monkeypatch, tmp_path: Path, capsys) -> None:
    module = _load_module()

    repo_root = tmp_path / "repo"
    target = repo_root / "README.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "Publish dist/JUDGE_ATLAS-main-final.zip only\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(module, "SCAN_GLOBS", ("README.md",))

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "RELEASE_NAMING_DRIFT: PASS" in out
