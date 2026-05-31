from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_handoff(
    path: Path,
    archive_rel: str,
    sha256: str,
    *,
    alpha_gate_passed: bool = True,
    release_candidate: bool = True,
    production_ready: bool = False,
    classification: str = "proof-hardened alpha release candidate",
    notes: list[str] | None = None,
    proof_anchor_lines: list[str] | None = None,
) -> None:
    note_lines = notes or [
        "- This is a proof-hardened alpha release candidate.",
        "- It is not ready for production deployment.",
    ]
    path.write_text(
        "\n".join(
            [
                "# Final Release Handoff",
                "",
                "- Path: " + archive_rel,
                "- SHA-256: " + sha256,
                "- release_classification: " + classification,
                f"- alpha_gate_passed: {str(alpha_gate_passed).lower()}",
                f"- release_candidate: {str(release_candidate).lower()}",
                f"- production_ready: {str(production_ready).lower()}",
                "",
                "## Proof Anchors",
                *(proof_anchor_lines or []),
                "",
                *note_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _module():
    return _load_module(
        "check_release_handoff_consistency_module",
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "check_release_handoff_consistency.py",
    )


def test_handoff_consistency_passes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "dist").mkdir(parents=True, exist_ok=True)
    (repo_root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    archive = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive.write_bytes(b"archive-bytes")
    release_gate = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    proof_manifest = repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    required_log_index = repo_root / "artifacts" / "proof" / "current" / "required_log_index.json"

    release_gate.write_text(
        '{"alpha_gate_passed": true, "release_candidate": true, "production_ready": false}',
        encoding="utf-8",
    )
    proof_manifest.write_text('{"proof_commands": []}', encoding="utf-8")
    required_log_index.write_text('{"entries": []}', encoding="utf-8")

    handoff = repo_root / "FINAL_RELEASE_HANDOFF.md"
    _write_handoff(
        handoff,
        "dist/JUDGE_ATLAS-main-final.zip",
        _sha256(archive),
        proof_anchor_lines=[
            "- release_gate_path: artifacts/proof/current/release_gate.json",
            f"- release_gate_sha256: {_sha256(release_gate)}",
            "- proof_manifest_path: artifacts/proof/current/proof_manifest.json",
            f"- proof_manifest_sha256: {_sha256(proof_manifest)}",
            "- required_log_index_path: artifacts/proof/current/required_log_index.json",
            f"- required_log_index_sha256: {_sha256(required_log_index)}",
        ],
    )

    module = _module()
    ok, errors = module.validate_handoff(repo_root, archive, handoff)
    assert ok
    assert not errors


def test_handoff_consistency_fails_on_sha_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "dist").mkdir(parents=True, exist_ok=True)
    (repo_root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    archive = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive.write_bytes(b"archive-bytes")
    (repo_root / "artifacts" / "proof" / "current" / "release_gate.json").write_text(
        '{"alpha_gate_passed": true, "release_candidate": true, "production_ready": false}',
        encoding="utf-8",
    )
    handoff = repo_root / "FINAL_RELEASE_HANDOFF.md"
    _write_handoff(
        handoff,
        "dist/JUDGE_ATLAS-main-final.zip",
        "0" * 64,
    )

    module = _module()
    ok, errors = module.validate_handoff(repo_root, archive, handoff)
    assert not ok
    assert any(err.startswith("sha256_mismatch:") for err in errors)


def test_handoff_consistency_fails_on_path_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "dist").mkdir(parents=True, exist_ok=True)
    (repo_root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    archive = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive.write_bytes(b"archive-bytes")
    (repo_root / "artifacts" / "proof" / "current" / "release_gate.json").write_text(
        '{"alpha_gate_passed": true, "release_candidate": true, "production_ready": false}',
        encoding="utf-8",
    )
    handoff = repo_root / "FINAL_RELEASE_HANDOFF.md"
    _write_handoff(handoff, "dist/other.zip", _sha256(archive))

    module = _module()
    ok, errors = module.validate_handoff(repo_root, archive, handoff)
    assert not ok
    assert any(err.startswith("archive_path_mismatch:") for err in errors)


def test_handoff_consistency_fails_on_missing_claims(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "dist").mkdir(parents=True, exist_ok=True)
    (repo_root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    archive = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive.write_bytes(b"archive-bytes")
    (repo_root / "artifacts" / "proof" / "current" / "release_gate.json").write_text(
        '{"alpha_gate_passed": true, "release_candidate": true, "production_ready": false}',
        encoding="utf-8",
    )
    handoff = repo_root / "FINAL_RELEASE_HANDOFF.md"
    handoff.write_text("# Final Release Handoff\n", encoding="utf-8")

    module = _module()
    ok, errors = module.validate_handoff(repo_root, archive, handoff)
    assert not ok
    assert "missing_claimed_path" in errors
    assert "missing_claimed_sha256" in errors


def test_handoff_consistency_fails_on_status_and_alpha_wording_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "dist").mkdir(parents=True, exist_ok=True)
    (repo_root / "artifacts" / "proof" / "current").mkdir(parents=True, exist_ok=True)
    archive = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive.write_bytes(b"archive-bytes")
    (repo_root / "artifacts" / "proof" / "current" / "release_gate.json").write_text(
        '{"alpha_gate_passed": true, "release_candidate": true, "production_ready": false}',
        encoding="utf-8",
    )
    handoff = repo_root / "FINAL_RELEASE_HANDOFF.md"
    _write_handoff(
        handoff,
        "dist/JUDGE_ATLAS-main-final.zip",
        _sha256(archive),
        alpha_gate_passed=False,
        release_candidate=False,
        classification="production release",
        notes=["- Ship only the archive listed above."],
    )

    module = _module()
    ok, errors = module.validate_handoff(repo_root, archive, handoff)
    assert not ok
    assert any(err.startswith("alpha_gate_passed_mismatch:") for err in errors)
    assert any(err.startswith("release_candidate_mismatch:") for err in errors)
    assert any(err.startswith("release_classification_mismatch:") for err in errors)
    assert "missing_not_production_ready_note" in errors
    assert "missing_alpha_wording" in errors

