from pathlib import Path

import pytest

from app.orchestration.task_registry import _resolve_workspace_relative_path


def test_workspace_relative_path_allows_simple_paths(tmp_path):
    workspace = str(tmp_path)

    assert _resolve_workspace_relative_path(workspace, "output.txt") == tmp_path / "output.txt"
    assert _resolve_workspace_relative_path(workspace, "nested/output.txt") == tmp_path / "nested" / "output.txt"


@pytest.mark.parametrize(
    "relative_path,expected_message",
    [
        ("", "Path must not be empty"),
        ("../escape.txt", "resolves outside workspace"),
        ("/etc/passwd", "must be relative to the workspace"),
        ("C:\\Windows\\system32\\drivers\\etc\\hosts", "must be relative to the workspace"),
    ],
)
def test_workspace_relative_path_rejects_invalid_inputs(tmp_path, relative_path, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        _resolve_workspace_relative_path(str(tmp_path), relative_path)


def test_workspace_relative_path_rejects_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (workspace / "escape").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="resolves outside workspace"):
        _resolve_workspace_relative_path(str(workspace), "escape/payload.txt")