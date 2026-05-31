"""Add unique constraint to relationship_evidence table.

Revision ID: 20260501_0008
Revises: 20260501_0007
Create Date: 2026-05-01
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_0008"
down_revision: Union[str, None] = "20260501_0007"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to relationship_evidence table."""
    with op.batch_alter_table("relationship_evidence") as batch_op:
        batch_op.create_unique_constraint(
            "uq_relationship_evidence_unique_edge",
            [
                "from_entity_type",
                "from_entity_id",
                "to_entity_type",
                "to_entity_id",
                "relationship_type",
            ],
        )


def downgrade() -> None:
    """Remove unique constraint from relationship_evidence table."""
    with op.batch_alter_table("relationship_evidence") as batch_op:
        batch_op.drop_constraint("uq_relationship_evidence_unique_edge", type_="unique")
