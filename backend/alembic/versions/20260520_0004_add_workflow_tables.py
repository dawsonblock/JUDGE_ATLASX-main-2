"""Add workflow execution tables.

Adds tables for tracking workflow definitions, runs, steps, artifacts,
schedules, and locks. These tables support the Osmedeus-style workflow
execution system using the existing Postgres queue infrastructure.

Revision ID: 20260520_0004
Revises: 20260520_0003
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260520_0004'
down_revision = '20260520_0003'
branch_labels = None
depends_on = None


def upgrade():
    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('workflow_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('workspace_path', sa.String(512), nullable=True),
        sa.Column('source_key', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id')
    )
    op.create_index('idx_workflow_runs_run_id', 'workflow_runs', ['run_id'])
    op.create_index('idx_workflow_runs_workflow_name', 'workflow_runs', ['workflow_name'])
    op.create_index('idx_workflow_runs_status', 'workflow_runs', ['status'])

    # Create workflow_steps table
    op.create_table(
        'workflow_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(255), nullable=False),
        sa.Column('step_type', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('output', sa.JSON(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'])
    )
    op.create_index('idx_workflow_steps_step_id', 'workflow_steps', ['step_id'])
    op.create_index('idx_workflow_steps_run_id', 'workflow_steps', ['run_id'])
    op.create_index('idx_workflow_steps_status', 'workflow_steps', ['status'])

    # Create workflow_artifacts table
    op.create_table(
        'workflow_artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('artifact_name', sa.String(255), nullable=False),
        sa.Column('artifact_path', sa.String(512), nullable=False),
        sa.Column('artifact_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('preserve', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id'])
    )

    # Create workflow_schedules table
    op.create_table(
        'workflow_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_name', sa.String(255), nullable=False),
        sa.Column('schedule', sa.String(100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_name')
    )
    op.create_index('idx_workflow_schedules_workflow_name', 'workflow_schedules', ['workflow_name'])

    # Create workflow_locks table
    op.create_table(
        'workflow_locks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_name', sa.String(255), nullable=False),
        sa.Column('locked_by', sa.String(255), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_name')
    )
    op.create_index('idx_workflow_locks_workflow_name', 'workflow_locks', ['workflow_name'])


def downgrade():
    # Drop workflow_locks table
    op.drop_index('idx_workflow_locks_workflow_name', table_name='workflow_locks')
    op.drop_table('workflow_locks')

    # Drop workflow_schedules table
    op.drop_index('idx_workflow_schedules_workflow_name', table_name='workflow_schedules')
    op.drop_table('workflow_schedules')

    # Drop workflow_artifacts table
    op.drop_table('workflow_artifacts')

    # Drop workflow_steps table
    op.drop_index('idx_workflow_steps_status', table_name='workflow_steps')
    op.drop_index('idx_workflow_steps_run_id', table_name='workflow_steps')
    op.drop_index('idx_workflow_steps_step_id', table_name='workflow_steps')
    op.drop_table('workflow_steps')

    # Drop workflow_runs table
    op.drop_index('idx_workflow_runs_status', table_name='workflow_runs')
    op.drop_index('idx_workflow_runs_workflow_name', table_name='workflow_runs')
    op.drop_index('idx_workflow_runs_run_id', table_name='workflow_runs')
    op.drop_table('workflow_runs')