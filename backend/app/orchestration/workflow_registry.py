"""Workflow registry for loading and validating YAML workflow definitions.

This module loads workflow YAML files from the workflows directory, validates
their schema, checks that source keys exist, validates step names against
allowed task types, and enforces safety constraints. It explicitly rejects
unknown steps and shell commands.
"""
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from app.models.entities import LegalSource

logger = logging.getLogger(__name__)

# Allowed step types - only safe, registered Python functions
ALLOWED_STEP_TYPES = {
    "fetch_url",
    "fetch_api",
    "evidence_snapshot",
    "parse_law_xml",
    "parse_court_events",
    "parse_police_release",
    "extract_claims",
    "resolve_entities",
    "geocode_locations",
    "dedupe_events",
    "contradiction_check",
    "confidence_score",
    "legal_correlation",
    "enqueue_review",
    "publish_map_layer",
}

# Blocked step types - explicitly forbidden for safety
BLOCKED_STEP_TYPES = {
    "shell",
    "bash",
    "exec",
    "remote_exec",
    "nmap",
    "shodan",
    "scanner",
    "exploit",
    "sigint",
    "radio",
    "cctv",
    "mesh",
    "wormhole",
    "installer",
    "tool_execution",
    "cloud_worker_auto_provision",
}


class WorkflowValidationError(Exception):
    """Raised when a workflow fails validation."""


class WorkflowDefinition:
    """Represents a loaded and validated workflow definition."""

    def __init__(self, name: str, definition: dict[str, Any], source_path: str):
        self.name = name
        self.definition = definition
        self.source_path = source_path

    @property
    def kind(self) -> str:
        return self.definition.get("kind", "unknown")

    @property
    def enabled(self) -> bool:
        return self.definition.get("enabled", False)

    @property
    def schedule(self) -> str | None:
        return self.definition.get("schedule")

    @property
    def jurisdiction(self) -> str | None:
        return self.definition.get("jurisdiction")

    @property
    def province(self) -> str | None:
        return self.definition.get("province")

    @property
    def steps(self) -> list[dict[str, Any]]:
        return self.definition.get("steps", [])

    @property
    def source_key(self) -> str | None:
        source_config = self.definition.get("source", {})
        return source_config.get("source_key")

    @property
    def source_type(self) -> str | None:
        source_config = self.definition.get("source", {})
        return source_config.get("source_type")


class WorkflowRegistry:
    """Registry for loading and validating workflow definitions."""

    def __init__(self, workflows_dir: str | None = None):
        if workflows_dir is None:
            # Default to backend/app/workflows
            current_dir = Path(__file__).parent.parent
            workflows_dir = str(current_dir / "workflows")

        self.workflows_dir = Path(workflows_dir)
        self.workflows: dict[str, WorkflowDefinition] = {}
        self._load_workflows()

    def _load_workflows(self) -> None:
        """Load all workflow YAML files from the workflows directory."""
        if not self.workflows_dir.exists():
            logger.warning(
                f"Workflows directory does not exist: {self.workflows_dir}"
            )
            return

        for workflow_file in self.workflows_dir.glob("*.yaml"):
            try:
                self._load_workflow_file(workflow_file)
            except Exception as e:
                logger.error(
                    f"Failed to load workflow {workflow_file}: {e}", exc_info=True
                )

        logger.info(f"Loaded {len(self.workflows)} workflows from registry")

    def _load_workflow_file(self, workflow_file: Path) -> None:
        """Load and validate a single workflow YAML file."""
        with open(workflow_file, "r") as f:
            definition = yaml.safe_load(f)

        workflow_name = definition.get("name")
        if not workflow_name:
            raise WorkflowValidationError(
                f"Workflow {workflow_file} missing 'name' field"
            )

        # Validate schema
        self._validate_schema(definition)

        # Create workflow definition
        workflow = WorkflowDefinition(
            name=workflow_name,
            definition=definition,
            source_path=str(workflow_file),
        )

        self.workflows[workflow_name] = workflow
        logger.info(f"Loaded workflow: {workflow_name}")

    def _validate_schema(self, definition: dict[str, Any]) -> None:
        """Validate workflow schema and safety constraints."""
        # Required fields
        required_fields = ["name", "kind", "enabled", "steps"]
        for field in required_fields:
            if field not in definition:
                raise WorkflowValidationError(
                    f"Workflow missing required field: {field}"
                )

        # Validate steps
        steps = definition.get("steps", [])
        if not steps:
            raise WorkflowValidationError("Workflow must have at least one step")

        for i, step in enumerate(steps):
            self._validate_step(step, i)

        # Validate source configuration
        source = definition.get("source", {})
        if not source.get("source_key"):
            raise WorkflowValidationError("Workflow source missing 'source_key'")

        # Validate review gate
        review_gate = definition.get("review_gate", {})
        if review_gate.get("required", False) and not review_gate.get("queue"):
            raise WorkflowValidationError(
                "Review gate required but no queue specified"
            )

    def _validate_step(self, step: dict[str, Any], step_index: int) -> None:
        """Validate a single workflow step."""
        if "uses" not in step:
            raise WorkflowValidationError(
                f"Step {step_index} missing 'uses' field"
            )

        step_type = step["uses"]

        # Check for blocked step types
        if step_type in BLOCKED_STEP_TYPES:
            raise WorkflowValidationError(
                f"Step {step_index} uses blocked step type: {step_type}"
            )

        # Check for allowed step types
        if step_type not in ALLOWED_STEP_TYPES:
            raise WorkflowValidationError(
                f"Step {step_index} uses unknown step type: {step_type}. "
                f"Allowed types: {', '.join(sorted(ALLOWED_STEP_TYPES))}"
            )

        # Validate step has an ID
        if "id" not in step:
            raise WorkflowValidationError(f"Step {step_index} missing 'id' field")

    def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get a workflow definition by name."""
        return self.workflows.get(name)

    def list_workflows(self, enabled_only: bool = False) -> list[WorkflowDefinition]:
        """List all workflows, optionally filtering by enabled status."""
        workflows = list(self.workflows.values())
        if enabled_only:
            workflows = [w for w in workflows if w.enabled]
        return workflows

    def validate_source_exists(
        self, workflow_name: str, db_session
    ) -> bool:
        """Check if the workflow's source key exists in the source registry."""
        workflow = self.get_workflow(workflow_name)
        if not workflow:
            return False

        source_key = workflow.source_key
        if not source_key:
            return False

        source = (
            db_session.query(LegalSource)
            .filter(LegalSource.source_id == source_key)
            .first()
        )

        return source is not None

    def reload(self) -> None:
        """Reload all workflows from the workflows directory."""
        self.workflows.clear()
        self._load_workflows()
