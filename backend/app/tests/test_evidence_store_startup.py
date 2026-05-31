from __future__ import annotations

from pathlib import Path

import pytest

from app.services.evidence_store_validation import validate_evidence_store_root


def test_missing_root_fails_when_required() -> None:
    with pytest.raises(RuntimeError, match="required but not configured"):
        validate_evidence_store_root(None, required=True)


def test_file_path_instead_of_directory_fails(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a directory"):
        validate_evidence_store_root(str(file_path), required=True)


def test_unwritable_root_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _deny_access(path: object, mode: int) -> bool:
        return False

    monkeypatch.setattr("app.services.evidence_store_validation.os.access", _deny_access)
    with pytest.raises(RuntimeError, match="not readable/writable/searchable"):
        validate_evidence_store_root(str(tmp_path), required=True)


def test_repo_internal_root_fails_in_production(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    inner = repo_root / "evidence"
    inner.mkdir()
    with pytest.raises(RuntimeError, match="must not be inside the application repo"):
        validate_evidence_store_root(
            str(inner),
            required=True,
            repo_root=str(repo_root),
        )


def test_valid_external_root_passes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    external = tmp_path / "external-evidence"
    external.mkdir()

    result = validate_evidence_store_root(
        str(external),
        required=True,
        repo_root=str(repo_root),
    )
    assert result["enabled"] is True
    assert result["reason"] is None
    assert result["snapshots_dir"] is not None


def test_non_required_allows_not_configured() -> None:
    result = validate_evidence_store_root(None, required=False)
    assert result["enabled"] is False
    assert result["reason"] == "not_configured"
