"""Add unique constraint to entity_graph_edges table.

Revision ID: 20260501_0009
Revises: 20260501_0008
Create Date: 2026-05-01
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0009"
down_revision: Union[str, None] = "20260501_0008"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to entity_graph_edges table."""
    # First, deduplicate existing data - keep only the oldest record (MIN id) for each group
    op.execute("""
        DELETE FROM entity_graph_edges
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM entity_graph_edges
            GROUP BY subject_type, subject_id, predicate, object_type, object_id, valid_from
        )
    """)

    with op.batch_alter_table("entity_graph_edges") as batch_op:
        batch_op.create_unique_constraint(
            "uq_entity_graph_edge_unique_temporal",
            [
                "subject_type",
                "subject_id",
                "predicate",
                "object_type",
                "object_id",
                "valid_from",
            ],
        )


def downgrade() -> None:
    """Remove unique constraint from entity_graph_edges table."""
    with op.batch_alter_table("entity_graph_edges") as batch_op:
        batch_op.drop_constraint("uq_entity_graph_edge_unique_temporal", type_="unique")
