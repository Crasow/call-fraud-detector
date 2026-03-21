"""add profiles table and profile_id to calls

Revision ID: 003
Revises: 002
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_mode", sa.String(20), nullable=False, server_default="custom"),
        sa.Column("custom_prompt", sa.Text(), nullable=True),
        sa.Column("expert", sa.String(255), nullable=True),
        sa.Column("main_task", sa.Text(), nullable=True),
        sa.Column("fields_for_json", sa.Text(), nullable=True),
        sa.Column("trigger_words", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.add_column(
        "calls",
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("calls", "profile_id")
    op.drop_table("profiles")
