"""Workflow step models for tracking step execution state.

This module defines the data models for workflow runs, steps, artifacts,
and schedules. These models represent the state machine for workflow execution.
"""
from datetime import datetime, timezone
from typing import Any
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class WorkflowRunStatus(str, Enum):
    """Status of a workflow run."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(str, Enum):
    """Status of a workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class WorkflowRun(Base):
    """Represents a single execution of a workflow."""
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), unique=True, nullable=False, index=True)
    workflow_name = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=WorkflowRunStatus.PENDING.value)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    workspace_path = Column(String(512), nullable=True)
    source_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    steps = relationship("WorkflowStep", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("WorkflowArtifact", back_populates="run", cascade="all, delete-orphan")


class WorkflowStep(Base):
    """Represents a single step in a workflow run."""
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True)
    step_id = Column(String(64), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    step_name = Column(String(255), nullable=False)
    step_type = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default=WorkflowStepStatus.PENDING.value)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    output = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    run = relationship("WorkflowRun", back_populates="steps")


class WorkflowArtifact(Base):
    """Represents an artifact produced by a workflow run."""
    __tablename__ = "workflow_artifacts"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    artifact_name = Column(String(255), nullable=False)
    artifact_path = Column(String(512), nullable=False)
    artifact_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    preserve = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    run = relationship("WorkflowRun", back_populates="artifacts")


class WorkflowSchedule(Base):
    """Represents a scheduled workflow execution."""
    __tablename__ = "workflow_schedules"

    id = Column(Integer, primary_key=True)
    workflow_name = Column(String(255), nullable=False, unique=True, index=True)
    schedule = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class WorkflowLock(Base):
    """Represents a lock to prevent concurrent workflow executions."""
    __tablename__ = "workflow_locks"

    id = Column(Integer, primary_key=True)
    workflow_name = Column(String(255), nullable=False, unique=True, index=True)
    locked_by = Column(String(255), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
