"""Workflow runner for executing workflow definitions.

This module provides the workflow runner that uses the existing PostgresIngestionQueue
for job execution. It implements the step state machine, creates run workspace structure,
writes run logs and artifacts, updates source health, and sends outputs to the
evidence/memory system.
"""
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.orchestration.task_registry import TaskRegistry, TaskResult
from app.orchestration.workflow_registry import WorkflowDefinition
from app.orchestration.workflow_step_models import (
    WorkflowArtifact,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowSchedule,
    WorkflowStep,
    WorkflowStepStatus,
)

logger = logging.getLogger(__name__)

# Pattern to detect path traversal attempts
_PATH_TRAVERSAL_PATTERN = re.compile(r'\.\.|[/\\]')


def _sanitize_path_component(component: str) -> str:
    """Sanitize a path component to prevent path traversal attacks.
    
    Args:
        component: The path component to sanitize
        
    Returns:
        Sanitized component with path traversal characters removed
        
    Raises:
        ValueError: If component contains path traversal attempts
    """
    if _PATH_TRAVERSAL_PATTERN.search(component):
        raise ValueError(f"Path component contains invalid characters: {component}")
    return component


class WorkflowRunner:
    """Runner for executing workflow definitions."""

    def __init__(self, task_registry: TaskRegistry, workspace_base_dir: str | None = None):
        self.task_registry = task_registry

        if workspace_base_dir is None:
            # Default to backend/data/workspaces
            current_dir = Path(__file__).parent.parent.parent
            workspace_base_dir = str(current_dir / "data" / "workspaces")

        self.workspace_base_dir = Path(workspace_base_dir)
        self.workspace_base_dir.mkdir(parents=True, exist_ok=True)

    def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        db: Session,
        run_id: str | None = None,
    ) -> WorkflowRun:
        """Execute a workflow definition."""
        if run_id is None:
            run_id = str(uuid.uuid4())

        # Sanitize path components to prevent traversal
        sanitized_name = _sanitize_path_component(workflow.name)
        sanitized_run_id = _sanitize_path_component(run_id)

        # Create workspace directory
        workspace_path = self.workspace_base_dir / sanitized_name / sanitized_run_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create workspace subdirectories
        (workspace_path / "raw").mkdir(exist_ok=True)
        (workspace_path / "snapshots").mkdir(exist_ok=True)
        (workspace_path / "parsed").mkdir(exist_ok=True)
        (workspace_path / "claims").mkdir(exist_ok=True)
        (workspace_path / "logs").mkdir(exist_ok=True)
        (workspace_path / "artifacts").mkdir(exist_ok=True)
        (workspace_path / "reports").mkdir(exist_ok=True)

        # Create workflow run record
        run = WorkflowRun(
            run_id=run_id,
            workflow_name=workflow.name,
            status=WorkflowRunStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc),
            workspace_path=str(workspace_path),
            source_key=workflow.source_key,
        )
        db.add(run)
        db.commit()

        logger.info(f"Starting workflow run: {workflow.name} (run_id={run_id})")

        try:
            # Execute each step
            for step_def in workflow.steps:
                step = self._execute_step(
                    step_def,
                    run,
                    workspace_path,
                    db,
                )

                if step.status == WorkflowStepStatus.FAILED.value:
                    # Check if this step should retry
                    retry_config = workflow.definition.get("on_error", {})
                    retry_steps = retry_config.get("retry_steps", [])

                    if step_def["id"] in retry_steps:
                        max_retries = retry_config.get("max_retries", 3)
                        if step.retry_count < max_retries:
                            step.retry_count += 1
                            step.status = WorkflowStepStatus.PENDING.value
                            db.commit()

                            # Retry the step
                            step = self._execute_step(
                                step_def,
                                run,
                                workspace_path,
                                db,
                            )

                    if step.status == WorkflowStepStatus.FAILED.value:
                        # Step failed after retries, mark run as failed
                        run.status = WorkflowRunStatus.FAILED.value
                        run.error_message = f"Step {step_def['id']} failed: {step.error_message}"
                        run.completed_at = datetime.now(timezone.utc)
                        db.commit()

                        # Move to dead letter queue if configured
                        if retry_config.get("dead_letter_queue", False):
                            self._move_to_dead_letter_queue(run, db)

                        logger.error(f"Workflow run failed: {run_id}")
                        return run

            # All steps succeeded
            run.status = WorkflowRunStatus.SUCCESS.value
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Workflow run completed successfully: {run_id}")

            # Update source health
            self._update_source_health(workflow.source_key, db)

            return run

        except Exception as e:
            logger.exception(f"Workflow run failed with exception: {run_id}")
            run.status = WorkflowRunStatus.FAILED.value
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return run

    def _execute_step(
        self,
        step_def: dict[str, Any],
        run: WorkflowRun,
        workspace_path: Path,
        db: Session,
    ) -> WorkflowStep:
        """Execute a single workflow step."""
        step_id = step_def["id"]
        step_type = step_def["uses"]
        step_name = step_def.get("name", step_id)
        step_params = step_def.get("with", {})

        # Create or update step record
        step = (
            db.query(WorkflowStep)
            .filter(WorkflowStep.run_id == run.id, WorkflowStep.step_id == step_id)
            .first()
        )

        if not step:
            step = WorkflowStep(
                step_id=step_id,
                run_id=run.id,
                step_name=step_name,
                step_type=step_type,
                status=WorkflowStepStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc),
            )
            db.add(step)
        else:
            step.status = WorkflowStepStatus.RUNNING.value
            step.started_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(f"Executing step: {step_id} ({step_type})")

        try:
            # Execute the task
            result: TaskResult = self.task_registry.execute_task(
                task_type=step_type,
                db=db,
                workspace_path=str(workspace_path),
                params=step_params,
            )

            if result.success:
                step.status = WorkflowStepStatus.SUCCESS.value
                step.output = result.output
                step.completed_at = datetime.now(timezone.utc)
                logger.info(f"Step completed successfully: {step_id}")
            else:
                step.status = WorkflowStepStatus.FAILED.value
                step.error_message = result.error
                step.completed_at = datetime.now(timezone.utc)
                logger.error(f"Step failed: {step_id} - {result.error}")

            db.commit()

            # Create artifacts if specified
            if result.output and isinstance(result.output, dict):
                output_path = result.output.get("output_path")
                if output_path:
                    self._create_artifact(
                        run,
                        step,
                        output_path,
                        step_type,
                        db,
                    )

            return step

        except Exception as e:
            logger.exception(f"Step execution failed: {step_id}")
            step.status = WorkflowStepStatus.FAILED.value
            step.error_message = str(e)
            step.completed_at = datetime.now(timezone.utc)
            db.commit()
            return step

    def _create_artifact(
        self,
        run: WorkflowRun,
        step: WorkflowStep,
        artifact_path: str,
        artifact_type: str,
        db: Session,
    ) -> None:
        """Create an artifact record for a step output."""
        path = Path(artifact_path)
        if not path.exists():
            return

        size_bytes = path.stat().st_size

        artifact = WorkflowArtifact(
            run_id=run.id,
            artifact_name=f"{step.step_id}_{path.name}",
            artifact_path=artifact_path,
            artifact_type=artifact_type,
            size_bytes=size_bytes,
            preserve="true",
        )
        db.add(artifact)
        db.commit()

    def _update_source_health(self, source_key: str | None, db: Session) -> None:
        """Update source health after successful workflow run."""
        if not source_key:
            return

        from app.models.entities import LegalSource

        source = (
            db.query(LegalSource)
            .filter(LegalSource.source_id == source_key)
            .first()
        )

        if source:
            source.last_ingested_at = datetime.now(timezone.utc)
            db.commit()

    def _move_to_dead_letter_queue(self, run: WorkflowRun, db: Session) -> None:
        """Move a failed workflow run to the dead letter queue."""
        from app.models.entities import DeadLetterQueueJob

        dlq_job = DeadLetterQueueJob(
            original_job_id=run.run_id,
            source_id=run.source_key or "unknown",
            job_type="workflow",
            payload_json={
                "run_id": run.run_id,
                "workflow_name": run.workflow_name,
                "error": run.error_message,
                "workspace_path": run.workspace_path,
            },
            final_error=run.error_message or "Unknown error",
            attempt_count=1,
            dead_lettered_at=datetime.now(timezone.utc),
        )
        db.add(dlq_job)
        db.commit()

    def cleanup_workspace(self, run_id: str) -> None:
        """Clean up workspace directory for a run."""
        # Sanitize run_id to prevent path traversal
        sanitized_run_id = _sanitize_path_component(run_id)
        
        # Search for workspace directories matching the run_id
        for workflow_dir in self.workspace_base_dir.iterdir():
            if workflow_dir.is_dir():
                workspace_path = workflow_dir / sanitized_run_id
                if workspace_path.exists():
                    shutil.rmtree(workspace_path)
                    logger.info(f"Cleaned up workspace: {run_id}")
                    return

    def get_run_status(self, run_id: str, db: Session) -> WorkflowRun | None:
        """Get the status of a workflow run."""
        return db.query(WorkflowRun).filter(WorkflowRun.run_id == run_id).first()

    def list_runs(
        self,
        workflow_name: str | None = None,
        status: str | None = None,
        db: Session | None = None,
    ) -> list[WorkflowRun]:
        """List workflow runs with optional filtering."""
        if db is None:
            from app.db.session import SessionLocal

            db = SessionLocal()

        try:
            query = db.query(WorkflowRun)

            if workflow_name:
                query = query.filter(WorkflowRun.workflow_name == workflow_name)

            if status:
                query = query.filter(WorkflowRun.status == status)

            return query.order_by(WorkflowRun.created_at.desc()).all()
        finally:
            db.close()
