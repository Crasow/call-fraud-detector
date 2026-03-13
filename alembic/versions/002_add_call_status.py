"""add call status fields

Revision ID: 002
Revises: 001
Create Date: 2026-03-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("calls", sa.Column("error_message", sa.Text(), nullable=True))
    # Mark existing rows as done since they already have analysis results
    op.execute("UPDATE calls SET status = 'done' WHERE EXISTS (SELECT 1 FROM analysis_results WHERE analysis_results.call_id = calls.id)")


def downgrade() -> None:
    op.drop_column("calls", "error_message")
    op.drop_column("calls", "status")
