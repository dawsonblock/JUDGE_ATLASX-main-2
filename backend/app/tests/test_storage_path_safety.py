from pathlib import Path

import pytest

from app.storage.storage_client import LocalStorageClient


def test_rejects_parent_traversal(tmp_path: Path) -> None:
    store = LocalStorageClient(str(tmp_path))

    with pytest.raises(ValueError, match="escapes storage root"):
        store._get_path("../secret.txt")


def test_rejects_absolute_path(tmp_path: Path) -> None:
    store = LocalStorageClient(str(tmp_path))

    with pytest.raises(ValueError, match="must be relative"):
        store._get_path("/etc/passwd")


def test_allows_nested_relative_key(tmp_path: Path) -> None:
    store = LocalStorageClient(str(tmp_path))

    path = store._get_path("evidence/abc/source.json")

    assert path.name == "source.json"
    assert path.parent.name == "abc"
    assert path.parent.parent.name == "evidence"
