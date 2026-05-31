from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_repo_proof_tree(root: Path) -> str:
    archive_path = root / "dist" / "JUDGE_ATLAS-main-final.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b"alpha-proof-archive")
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()

    _write(
        root / "FINAL_RELEASE_HANDOFF.md",
        "\n".join(
            [
                "# FINAL_RELEASE_HANDOFF",
                "- Path: dist/JUDGE_ATLAS-main-final.zip",
                f"- SHA-256: {archive_sha}",
            ]
        )
        + "\n",
    )

    _write(
        root / "artifacts" / "proof" / "current" / "release_gate.json",
        json.dumps(
            {
                "alpha_gate_passed": True,
                "production_ready": False,
                "checks": [
                    {
                        "name": "archive_validation",
                        "status": "PASS",
                    }
                ],
            }
        )
        + "\n",
    )
    _write(
        root / "artifacts" / "proof" / "current" / "proof_manifest.json",
        json.dumps({"ok": True}) + "\n",
    )
    _write(
        root / "artifacts" / "proof" / "current" / "release_readiness.md",
        "- overall_status: alpha-proof-pass\n",
    )
    _write(
        root / "artifacts" / "proof" / "current" / "proof_freshness.log",
        "PROOF_FRESHNESS: PASS\n",
    )
    release_gate_log = root / "artifacts" / "proof" / "current" / "release_gate.log"
    _write(release_gate_log, "release gate pass\n")
    _write(
        root / "artifacts" / "proof" / "current" / "required_log_index.json",
        json.dumps(
            {
                "missing_required_logs": [],
                "entries": [
                    {
                        "path": "artifacts/proof/current/release_gate.log",
                        "exists": True,
                        "status": "PASS",
                        "recorded_sha256": hashlib.sha256(
                            release_gate_log.read_bytes()
                        ).hexdigest(),
                        "recorded_size_bytes": release_gate_log.stat().st_size,
                    }
                ],
            }
        )
        + "\n",
    )

    return archive_sha


def test_alpha_readiness_requires_concrete_proof_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.api.routes import status as status_routes

    repo_root = tmp_path / "repo"
    _seed_repo_proof_tree(repo_root)
    monkeypatch.setattr(status_routes, "_repo_root", lambda: repo_root)

    response = client.get("/api/v1/status/alpha-readiness")
    assert response.status_code == 200
    payload = response.json()

    assert payload["proof_chain_complete"] is True
    assert payload["archive_self_verifying"] is True


def test_alpha_readiness_fails_when_required_log_missing_on_disk(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.api.routes import status as status_routes

    repo_root = tmp_path / "repo"
    _seed_repo_proof_tree(repo_root)
    (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "release_gate.log"
    ).unlink()
    monkeypatch.setattr(status_routes, "_repo_root", lambda: repo_root)

    response = client.get("/api/v1/status/alpha-readiness")
    assert response.status_code == 200
    payload = response.json()

    assert payload["proof_chain_complete"] is False
    assert "required_log_missing_on_disk" in payload["warnings"]


def test_alpha_readiness_fails_when_proof_freshness_log_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.api.routes import status as status_routes

    repo_root = tmp_path / "repo"
    _seed_repo_proof_tree(repo_root)
    (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "proof_freshness.log"
    ).unlink()
    monkeypatch.setattr(status_routes, "_repo_root", lambda: repo_root)

    response = client.get("/api/v1/status/alpha-readiness")
    assert response.status_code == 200
    payload = response.json()

    assert payload["proof_chain_complete"] is False
    assert "proof_freshness_missing_or_failed" in payload["warnings"]
