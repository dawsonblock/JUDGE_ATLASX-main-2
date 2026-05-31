from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_truth_claims.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_truth_claims", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_non_allowlisted_docs_phrase_fails(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    phrase = "production" + "-ready"
    _write_file(root / "README.md", f"This platform is {phrase}.\n")

    assert module.check(root) == 1


def test_allowlisted_policy_phrase_passes(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    phrase = "production" + "-ready"
    _write_file(
        root / "scripts" / "verify_status_consistency.py",
        f"pattern = '{phrase}'\n",
    )

    assert module.check(root) == 0


def test_status_false_line_allowed(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    _write_file(root / "STATUS.md", "Production ready: FALSE\n")

    assert module.check(root) == 0
