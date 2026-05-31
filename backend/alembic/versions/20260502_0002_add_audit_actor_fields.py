"""Add actor identity fields to audit_logs table.

Revision ID: 20260502_0002
Revises: 20260502_0001
Create Date: 2026-05-02

Adds actor identity fields:
- actor_id: stable non-secret label (e.g. "shared-admin-token")
- actor_type: e.g. "shared_token", "user", "service"
- actor_role: e.g. "system_admin", "reviewer"
- user_agent: request user agent string
- request_id: correlation ID for the request
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260502_0002"
down_revision: Union[str, None] = "20260502_0001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Add actor identity fields to audit_logs."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("actor_id", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("actor_type", sa.String(80), nullable=True))
        batch_op.add_column(sa.Column("actor_role", sa.String(80), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(512), nullable=True))
        batch_op.add_column(sa.Column("request_id", sa.String(64), nullable=True))


def downgrade() -> None:
    """Remove actor identity fields from audit_logs."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_column("request_id")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("actor_role")
        batch_op.drop_column("actor_type")
        batch_op.drop_column("actor_id")
