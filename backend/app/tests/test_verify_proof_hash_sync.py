from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "verify_proof_hash_sync.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_proof_hash_sync", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed(root: Path, hash_value: str) -> None:
    proof_dir = root / "artifacts" / "proof" / "current"
    _write(
        proof_dir / "release_gate.json",
        json.dumps({"proof_input_tree_hash": hash_value}, indent=2) + "\n",
    )
    _write(
        proof_dir / "CURRENT_PROOF.md",
        f"- proof_input_tree_hash: {hash_value}\n",
    )
    _write(
        proof_dir / "proof_freshness.log",
        f"proof_input_tree_hash={hash_value}\n",
    )
    _write(
        proof_dir / "archive_validation.log",
        (
            "release_gate.json "
            f"proof_input_tree_hash={hash_value}\n"
            f"proof_freshness actual_hash={hash_value}\n"
        ),
    )


def test_verify_proof_hash_sync_passes_when_all_hashes_match(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    hash_value = "a" * 64
    _seed(root, hash_value)

    ok, errors, values = module.verify_hash_sync(root)

    assert ok is True
    assert errors == []
    assert set(values.values()) == {hash_value}


def test_verify_proof_hash_sync_fails_on_mismatch(tmp_path: Path) -> None:
    module = _load_module()
    root = tmp_path / "repo"
    hash_value = "b" * 64
    _seed(root, hash_value)
    _write(
        root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md",
        f"- proof_input_tree_hash: {'c' * 64}\n",
    )

    ok, errors, values = module.verify_hash_sync(root)

    assert ok is False
    assert "hash_mismatch" in errors
    assert values["release_gate.json"] == hash_value
    assert values["CURRENT_PROOF.md"] == "c" * 64
