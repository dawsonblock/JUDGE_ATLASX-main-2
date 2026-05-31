"""Workflow admin API endpoints for managing workflows.

This module provides admin endpoints for:
- Viewing workflows and runs
- Triggering workflow runs
- Pausing/resuming workflows
- Retrying failed runs
- Viewing step logs and artifacts
- Viewing source health
- Viewing created events and claims
- Viewing review queue

Experimental route module.
Not mounted in the runtime API until authorization and public-boundary
tests pass.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.actor import AdminActor
from app.auth.admin import enforce_jwt_mutation_authority, log_mutation
from app.db.session import get_db
from app.orchestration.task_registry import TaskRegistry
from app.orchestration.workflow_registry import WorkflowRegistry
from app.orchestration.workflow_runner import WorkflowRunner
from app.orchestration.workflow_step_models import (
    WorkflowArtifact,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowSchedule,
    WorkflowStep,
)
from app.security.import_authority import require_source_admin_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/workflows", tags=["workflow-admin"])


@router.get("/")
def list_workflows(
    enabled_only: bool = False,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """List all workflows."""
    workflow_registry = WorkflowRegistry()
    workflows = workflow_registry.list_workflows(enabled_only=enabled_only)

    return {
        "workflows": [
            {
                "name": w.name,
                "kind": w.kind,
                "enabled": w.enabled,
                "schedule": w.schedule,
                "jurisdiction": w.jurisdiction,
                "province": w.province,
                "source_key": w.source_key,
                "source_type": w.source_type,
                "step_count": len(w.steps),
            }
            for w in workflows
        ]
    }


@router.get("/runs")
def list_all_workflow_runs(
    workflow_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Compatibility endpoint for frontend panels listing workflow runs."""
    query = db.query(WorkflowRun)
    if workflow_name:
        query = query.filter(WorkflowRun.workflow_name == workflow_name)
    if status:
        query = query.filter(WorkflowRun.status == status)

    runs = query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()
    return {
        "runs": [
            {
                "id": run.id,
                "run_id": run.run_id,
                "workflow_name": run.workflow_name,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "error_message": run.error_message,
                "workspace_path": run.workspace_path,
                "source_key": run.source_key,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            }
            for run in runs
        ]
    }


@router.get("/runs/{run_id}")
def get_workflow_run(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Get details of a specific workflow run."""
    run = db.query(WorkflowRun).filter(WorkflowRun.run_id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get steps for this run
    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.run_id == run.id)
        .order_by(WorkflowStep.created_at)
        .all()
    )

    # Get artifacts for this run
    artifacts = (
        db.query(WorkflowArtifact)
        .filter(WorkflowArtifact.run_id == run.id)
        .all()
    )

    return {
        "run": {
            "run_id": run.run_id,
            "workflow_name": run.workflow_name,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error_message": run.error_message,
            "workspace_path": run.workspace_path,
            "source_key": run.source_key,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        },
        "steps": [
            {
                "step_id": step.step_id,
                "step_name": step.step_name,
                "step_type": step.step_type,
                "status": step.status,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
                "error_message": step.error_message,
                "retry_count": step.retry_count,
            }
            for step in steps
        ],
        "artifacts": [
            {
                "artifact_name": artifact.artifact_name,
                "artifact_path": artifact.artifact_path,
                "artifact_type": artifact.artifact_type,
                "size_bytes": artifact.size_bytes,
                "preserve": artifact.preserve,
            }
            for artifact in artifacts
        ],
    }


@router.get("/runs/{run_id}/steps")
def get_workflow_run_steps(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Compatibility endpoint for frontend step panel."""
    run = db.query(WorkflowRun).filter(WorkflowRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.run_id == run.id)
        .order_by(WorkflowStep.created_at)
        .all()
    )
    return {
        "steps": [
            {
                "id": step.id,
                "step_id": step.step_id,
                "run_id": run.id,
                "step_name": step.step_name,
                "step_type": step.step_type,
                "status": step.status,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
                "error_message": step.error_message,
                "output": step.output,
                "retry_count": step.retry_count,
            }
            for step in steps
        ]
    }


@router.post("/runs/{run_id}/retry")
def retry_workflow_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Retry a failed workflow run."""
    enforce_jwt_mutation_authority(actor)
    run = db.query(WorkflowRun).filter(WorkflowRun.run_id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status != WorkflowRunStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail="Only failed runs can be retried",
        )

    # Get workflow definition
    workflow_registry = WorkflowRegistry()
    workflow = workflow_registry.get_workflow(run.workflow_name)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Execute workflow with same run_id
    task_registry = TaskRegistry()
    runner = WorkflowRunner(task_registry)

    try:
        new_run = runner.execute_workflow(workflow, db, run_id=run_id)
        log_mutation(
            action="workflow.run.retry",
            entity_type="workflow_run",
            entity_id=run_id,
            payload={
                "run_id": run_id,
                "workflow_name": workflow.name,
                "status": new_run.status,
            },
            request=request,
            actor=actor,
            db=db,
            fail_closed=True,
        )
        return {
            "run_id": new_run.run_id,
            "status": new_run.status,
            "message": "Workflow run retried successfully",
        }
    except Exception as e:
        logger.error(f"Failed to retry workflow run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/logs")
def get_run_logs(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Get logs for a workflow run."""
    run = db.query(WorkflowRun).filter(WorkflowRun.run_id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get steps for this run
    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.run_id == run.id)
        .order_by(WorkflowStep.created_at)
        .all()
    )

    return {
        "run_id": run.run_id,
        "workflow_name": run.workflow_name,
        "status": run.status,
        "logs": [
            {
                "step_id": step.step_id,
                "step_name": step.step_name,
                "status": step.status,
                "error_message": step.error_message,
                "started_at": step.started_at,
                "completed_at": step.completed_at,
            }
            for step in steps
        ],
    }


@router.get("/schedules")
def list_schedules(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """List all workflow schedules."""
    schedules = db.query(WorkflowSchedule).all()

    return {
        "schedules": [
            {
                "workflow_name": schedule.workflow_name,
                "schedule": schedule.schedule,
                "enabled": schedule.enabled,
                "last_run_at": schedule.last_run_at,
                "next_run_at": schedule.next_run_at,
            }
            for schedule in schedules
        ]
    }


@router.post("/schedules/{workflow_name}/pause")
def pause_schedule(
    workflow_name: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Pause a scheduled workflow."""
    enforce_jwt_mutation_authority(actor)
    schedule = (
        db.query(WorkflowSchedule)
        .filter(WorkflowSchedule.workflow_name == workflow_name)
        .first()
    )

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = False
    db.commit()

    log_mutation(
        action="workflow.schedule.pause",
        entity_type="workflow_schedule",
        entity_id=workflow_name,
        payload={"workflow_name": workflow_name, "enabled": False},
        request=request,
        actor=actor,
        db=db,
        fail_closed=True,
    )

    return {"message": "Schedule paused successfully"}


@router.post("/schedules/{workflow_name}/resume")
def resume_schedule(
    workflow_name: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Resume a paused scheduled workflow."""
    enforce_jwt_mutation_authority(actor)
    schedule = (
        db.query(WorkflowSchedule)
        .filter(WorkflowSchedule.workflow_name == workflow_name)
        .first()
    )

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = True
    db.commit()

    log_mutation(
        action="workflow.schedule.resume",
        entity_type="workflow_schedule",
        entity_id=workflow_name,
        payload={"workflow_name": workflow_name, "enabled": True},
        request=request,
        actor=actor,
        db=db,
        fail_closed=True,
    )

    return {"message": "Schedule resumed successfully"}


@router.get("/{workflow_name}")
def get_workflow(
    workflow_name: str,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Get workflow details by name."""
    workflow_registry = WorkflowRegistry()
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "name": workflow.name,
        "kind": workflow.kind,
        "enabled": workflow.enabled,
        "schedule": workflow.schedule,
        "jurisdiction": workflow.jurisdiction,
        "province": workflow.province,
        "source_key": workflow.source_key,
        "source_type": workflow.source_type,
        "steps": workflow.steps,
    }


@router.get("/{workflow_name}/runs")
def list_workflow_runs(
    workflow_name: str,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """List runs for a specific workflow."""
    query = db.query(WorkflowRun).filter(
        WorkflowRun.workflow_name == workflow_name
    )

    if status:
        query = query.filter(WorkflowRun.status == status)

    runs = query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()

    return {
        "runs": [
            {
                "id": run.id,
                "run_id": run.run_id,
                "status": run.status,
                "workflow_name": run.workflow_name,
                "workspace_path": run.workspace_path,
                "source_key": run.source_key,
                "updated_at": run.updated_at,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "error_message": run.error_message,
                "created_at": run.created_at,
            }
            for run in runs
        ]
    }


@router.post("/{workflow_name}/run")
def trigger_workflow_run(
    workflow_name: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, Any]:
    """Trigger an immediate workflow run."""
    enforce_jwt_mutation_authority(actor)
    workflow_registry = WorkflowRegistry()
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.enabled:
        raise HTTPException(status_code=400, detail="Workflow is disabled")

    # Validate source exists
    if not workflow_registry.validate_source_exists(workflow_name, db):
        raise HTTPException(
            status_code=400,
            detail="Workflow source not found in registry",
        )

    # Execute workflow
    task_registry = TaskRegistry()
    runner = WorkflowRunner(task_registry)

    try:
        run = runner.execute_workflow(workflow, db)
        log_mutation(
            action="workflow.run.trigger",
            entity_type="workflow",
            entity_id=workflow_name,
            payload={"workflow_name": workflow_name, "run_id": run.run_id},
            request=request,
            actor=actor,
            db=db,
            fail_closed=True,
        )
        return {
            "run_id": run.run_id,
            "status": run.status,
            "message": "Workflow run triggered successfully",
        }
    except Exception as e:
        logger.error(f"Failed to trigger workflow run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
