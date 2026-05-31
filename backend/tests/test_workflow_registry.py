"""Tests for workflow registry."""
import pytest
from app.orchestration.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistry,
    WorkflowValidationError,
)


def test_workflow_definition_properties():
    """Test WorkflowDefinition property accessors."""
    definition = {
        "name": "test_workflow",
        "kind": "ingestion",
        "enabled": True,
        "schedule": "0 2 * * *",
        "jurisdiction": "federal",
        "province": None,
        "country": "Canada",
        "steps": [
            {
                "id": "step1",
                "uses": "fetch_url",
                "with": {"url": "https://example.com"},
            }
        ],
        "source": {
            "source_key": "test_source",
            "source_type": "official_government_open_data",
        },
    }

    workflow = WorkflowDefinition(
        name="test_workflow",
        definition=definition,
        source_path="/path/to/workflow.yaml",
    )

    assert workflow.name == "test_workflow"
    assert workflow.kind == "ingestion"
    assert workflow.enabled is True
    assert workflow.schedule == "0 2 * * *"
    assert workflow.jurisdiction == "federal"
    assert workflow.province is None
    assert workflow.source_key == "test_source"
    assert workflow.source_type == "official_government_open_data"
    assert len(workflow.steps) == 1


def test_workflow_registry_validation():
    """Test workflow registry validates schema."""
    registry = WorkflowRegistry(workflows_dir="/nonexistent")

    # Valid workflow definition
    valid_definition = {
        "name": "test_workflow",
        "kind": "ingestion",
        "enabled": True,
        "steps": [
            {
                "id": "step1",
                "uses": "fetch_url",
                "with": {"url": "https://example.com"},
            }
        ],
        "source": {"source_key": "test_source"},
    }

    # Should not raise exception
    registry._validate_schema(valid_definition)


def test_workflow_registry_blocked_step():
    """Test workflow registry rejects blocked step types."""
    registry = WorkflowRegistry(workflows_dir="/nonexistent")

    invalid_definition = {
        "name": "test_workflow",
        "kind": "ingestion",
        "enabled": True,
        "steps": [
            {
                "id": "step1",
                "uses": "shell",  # Blocked step type
                "with": {"command": "echo test"},
            }
        ],
        "source": {"source_key": "test_source"},
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        registry._validate_schema(invalid_definition)

    assert "blocked step type" in str(exc_info.value).lower()


def test_workflow_registry_unknown_step():
    """Test workflow registry rejects unknown step types."""
    registry = WorkflowRegistry(workflows_dir="/nonexistent")

    invalid_definition = {
        "name": "test_workflow",
        "kind": "ingestion",
        "enabled": True,
        "steps": [
            {
                "id": "step1",
                "uses": "unknown_step_type",  # Unknown step type
                "with": {},
            }
        ],
        "source": {"source_key": "test_source"},
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        registry._validate_schema(invalid_definition)

    assert "unknown step type" in str(exc_info.value).lower()


def test_workflow_registry_missing_required_field():
    """Test workflow registry requires all required fields."""
    registry = WorkflowRegistry(workflows_dir="/nonexistent")

    invalid_definition = {
        "name": "test_workflow",
        "kind": "ingestion",
        # Missing "enabled" field
        "steps": [],
        "source": {"source_key": "test_source"},
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        registry._validate_schema(invalid_definition)

    assert "required field" in str(exc_info.value).lower()
