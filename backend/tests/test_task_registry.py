"""Tests for task registry."""
import pytest
from app.orchestration.task_registry import TaskRegistry, TaskResult


def test_task_registry_initialization():
    """Test TaskRegistry initialization."""
    registry = TaskRegistry()

    # Should have default tasks registered
    assert len(registry.tasks) > 0
    assert "fetch_url" in registry.tasks
    assert "evidence_snapshot" in registry.tasks
    assert "contradiction_check" in registry.tasks


def test_task_registry_register():
    """Test registering a custom task."""
    registry = TaskRegistry()

    def custom_task(db, workspace_path, params):
        return {"custom": "result"}

    registry.register("custom_task", custom_task)

    assert "custom_task" in registry.tasks
    assert registry.get_task("custom_task") is custom_task


def test_task_result_creation():
    """Test TaskResult creation."""
    result = TaskResult(
        success=True,
        output={"key": "value"},
        error=None,
        metadata={"meta": "data"},
    )

    assert result.success is True
    assert result.output == {"key": "value"}
    assert result.error is None
    assert result.metadata == {"meta": "data"}


def test_task_result_to_dict():
    """Test converting TaskResult to dictionary."""
    result = TaskResult(
        success=False,
        output=None,
        error="Test error",
        metadata={},
    )

    result_dict = result.to_dict()

    assert result_dict["success"] is False
    assert result_dict["error"] == "Test error"
    assert result_dict["output"] is None


def test_task_registry_get_task_unknown():
    """Test getting unknown task returns None."""
    registry = TaskRegistry()

    task = registry.get_task("unknown_task_type")

    assert task is None


def test_task_registry_execute_task_unknown():
    """Test executing unknown task returns error result."""
    registry = TaskRegistry()

    result = registry.execute_task(
        task_type="unknown_task",
        db=None,
        workspace_path="/tmp/test",
        params={},
    )

    assert result.success is False
    assert result.error is not None
    assert "Unknown task type" in result.error


def test_task_registry_blocked_step_not_registered():
    """Test that blocked step types are not registered."""
    registry = TaskRegistry()

    # Blocked step types should not be in registry
    assert "shell" not in registry.tasks
    assert "bash" not in registry.tasks
    assert "exec" not in registry.tasks
    assert "nmap" not in registry.tasks
    assert "scanner" not in registry.tasks
