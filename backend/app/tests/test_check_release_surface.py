from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_release_surface.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_release_surface", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_zip(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)


def test_release_surface_accepts_clean_archive(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "clean.zip"
    _write_zip(
        archive,
        {
            "JUDGE_ATLAS-main/README.md": "ok\n",
            "JUDGE_ATLAS-main/STATUS.md": "Production ready: FALSE\n",
            "JUDGE_ATLAS-main/artifacts/proof/current/CURRENT_PROOF.md": "proof\n",
        },
    )

    report = module.inspect_surface(archive)

    assert report["valid"] is True
    assert report["errors"] == []


def test_release_surface_rejects_dirty_archive(tmp_path: Path) -> None:
    module = _load_module()
    archive = tmp_path / "dirty.zip"
    _write_zip(
        archive,
        {
            "JUDGE_ATLAS-main/README.md": "ok\n",
            "JUDGE_ATLAS-main/external/reference/README.md": "bad\n",
            "JUDGE_ATLAS-main/.env": "SECRET=1\n",
        },
    )

    report = module.inspect_surface(archive)

    assert report["valid"] is False
    assert "forbidden_release_surface_paths" in report["errors"]
    assert any("external" in path or "/.env" in path for path in report["forbidden_paths"])
