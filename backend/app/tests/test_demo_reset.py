from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def _load_reset_module():
    script_path = Path(__file__).resolve().parents[3] / "demo" / "scripts" / "reset_demo_data.py"
    module_name = "demo_reset_data_module"
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_reset_refuses_non_demo_sqlite_path_without_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_reset_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path / "repo")
    (tmp_path / "repo" / "demo").mkdir(parents=True)

    external_db = tmp_path / "external.sqlite3"
    external_db.write_text("x", encoding="utf-8")

    monkeypatch.delenv("JTA_DEMO_ALLOW_DB_DELETE", raising=False)
    with pytest.raises(ValueError, match="refusing to delete non-demo"):
        module._path_from_sqlite_url(f"sqlite:///{external_db}")


def test_demo_reset_allows_demo_sqlite_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_reset_module()
    repo_root = tmp_path / "repo"
    demo_root = repo_root / "demo"
    demo_root.mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)

    demo_db = demo_root / "demo.sqlite3"
    demo_db.write_text("x", encoding="utf-8")

    resolved = module._path_from_sqlite_url(f"sqlite:///{demo_db}")
    assert resolved == demo_db.resolve()


def test_demo_reset_requires_explicit_override_for_external_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_reset_module()
    repo_root = tmp_path / "repo"
    (repo_root / "demo").mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)

    external_db = tmp_path / "outside.sqlite3"
    external_db.write_text("x", encoding="utf-8")

    monkeypatch.setenv("JTA_DEMO_ALLOW_DB_DELETE", "1")
    monkeypatch.delenv("JTA_DEMO_CONFIRM_PATH", raising=False)
    with pytest.raises(ValueError, match="JTA_DEMO_CONFIRM_PATH"):
        module._path_from_sqlite_url(f"sqlite:///{external_db}")

    monkeypatch.setenv("JTA_DEMO_CONFIRM_PATH", str(external_db.resolve()))
    resolved = module._path_from_sqlite_url(f"sqlite:///{external_db}")
    assert resolved == external_db.resolve()


def test_demo_reset_never_deletes_non_sqlite_url(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_reset_module()
    monkeypatch.delenv("JTA_DEMO_ALLOW_DB_DELETE", raising=False)

    with pytest.raises(ValueError, match="only supports sqlite"):
        module._path_from_sqlite_url("postgresql://user:pass@localhost/db")


def test_demo_reset_does_not_follow_symlink_outside_demo_without_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_reset_module()
    repo_root = tmp_path / "repo"
    demo_root = repo_root / "demo"
    demo_root.mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)

    target_db = tmp_path / "outside.sqlite3"
    target_db.write_text("x", encoding="utf-8")
    link_path = demo_root / "demo.sqlite3"

    if hasattr(os, "symlink"):
        os.symlink(target_db, link_path)
    else:
        pytest.skip("symlink not supported on this platform")

    monkeypatch.delenv("JTA_DEMO_ALLOW_DB_DELETE", raising=False)
    with pytest.raises(ValueError, match="symlink"):
        module._path_from_sqlite_url(f"sqlite:///{link_path}")
