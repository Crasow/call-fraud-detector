"""initial_tables

Revision ID: 001
Revises:
Create Date: 2026-03-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("audio_format", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="upload"),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("is_fraud", sa.Boolean(), nullable=False),
        sa.Column("fraud_score", sa.Float(), nullable=False),
        sa.Column("fraud_categories", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("reasons", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("calls")
