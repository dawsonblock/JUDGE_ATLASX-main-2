"""Add graph layer: entity_graph_edges and court_events tables

Revision ID: 20260501_0004
Revises: 20260501_0003
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260501_0004'
down_revision: Union[str, Sequence[str], None] = '20260501_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create graph layer tables."""
    # Entity graph edges table
    op.create_table(
        'entity_graph_edges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_type', sa.String(length=50), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('predicate', sa.String(length=50), nullable=False),
        sa.Column('object_type', sa.String(length=50), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('evidence_refs', sa.JSON(), nullable=True),
        sa.Column('source_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=50), server_default='ingestion', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['source_snapshot_id'], ['source_snapshots.id'], name='fk_graph_edges_snapshot'),
        sa.PrimaryKeyConstraint('id'),
        sqlite_autoincrement=True
    )

    # Create indexes for graph edges
    op.create_index(op.f('ix_entity_graph_edges_subject_type'), 'entity_graph_edges', ['subject_type'], unique=False)
    op.create_index(op.f('ix_entity_graph_edges_subject_id'), 'entity_graph_edges', ['subject_id'], unique=False)
    op.create_index(op.f('ix_entity_graph_edges_predicate'), 'entity_graph_edges', ['predicate'], unique=False)
    op.create_index(op.f('ix_entity_graph_edges_object_type'), 'entity_graph_edges', ['object_type'], unique=False)
    op.create_index(op.f('ix_entity_graph_edges_object_id'), 'entity_graph_edges', ['object_id'], unique=False)
    op.create_index(op.f('ix_entity_graph_edges_status'), 'entity_graph_edges', ['status'], unique=False)
    op.create_index(
        'ix_graph_edges_subject_predicate',
        'entity_graph_edges',
        ['subject_type', 'subject_id', 'predicate'],
        unique=False
    )
    op.create_index(
        'ix_graph_edges_object_predicate',
        'entity_graph_edges',
        ['object_type', 'object_id', 'predicate'],
        unique=False
    )

    # Court events table
    op.create_table(
        'court_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=True),
        sa.Column('judge_id', sa.Integer(), nullable=True),
        sa.Column('court_id', sa.Integer(), nullable=True),
        sa.Column('documents', sa.JSON(), nullable=True),
        sa.Column('source_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('source_url', sa.String(length=2048), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_court_events_case'),
        sa.ForeignKeyConstraint(['court_id'], ['canonical_entities.id'], name='fk_court_events_court'),
        sa.ForeignKeyConstraint(['judge_id'], ['canonical_entities.id'], name='fk_court_events_judge'),
        sa.ForeignKeyConstraint(['source_snapshot_id'], ['source_snapshots.id'], name='fk_court_events_snapshot'),
        sa.PrimaryKeyConstraint('id'),
        sqlite_autoincrement=True
    )

    # Create indexes for court events
    op.create_index(op.f('ix_court_events_case_id'), 'court_events', ['case_id'], unique=False)
    op.create_index(op.f('ix_court_events_event_type'), 'court_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_court_events_event_date'), 'court_events', ['event_date'], unique=False)
    op.create_index(op.f('ix_court_events_judge_id'), 'court_events', ['judge_id'], unique=False)
    op.create_index(op.f('ix_court_events_court_id'), 'court_events', ['court_id'], unique=False)


def downgrade() -> None:
    """Drop graph layer tables."""
    op.drop_index(op.f('ix_court_events_court_id'), table_name='court_events')
    op.drop_index(op.f('ix_court_events_judge_id'), table_name='court_events')
    op.drop_index(op.f('ix_court_events_event_date'), table_name='court_events')
    op.drop_index(op.f('ix_court_events_event_type'), table_name='court_events')
    op.drop_index(op.f('ix_court_events_case_id'), table_name='court_events')
    op.drop_table('court_events')

    op.drop_index('ix_graph_edges_object_predicate', table_name='entity_graph_edges')
    op.drop_index('ix_graph_edges_subject_predicate', table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_status'), table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_object_id'), table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_object_type'), table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_predicate'), table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_subject_id'), table_name='entity_graph_edges')
    op.drop_index(op.f('ix_entity_graph_edges_subject_type'), table_name='entity_graph_edges')
    op.drop_table('entity_graph_edges')
