"""Add allowed_paths and pre_approved_commands to task_packets.

Revision ID: 007
Revises: 006
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    cols = [c["name"] for c in inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    bind = op.get_bind()
    col_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()

    if not _column_exists("task_packets", "allowed_paths"):
        op.add_column("task_packets", sa.Column("allowed_paths", col_type, nullable=True))

    if not _column_exists("task_packets", "pre_approved_commands"):
        op.add_column("task_packets", sa.Column("pre_approved_commands", col_type, nullable=True))


def downgrade() -> None:
    if _column_exists("task_packets", "pre_approved_commands"):
        op.drop_column("task_packets", "pre_approved_commands")
    if _column_exists("task_packets", "allowed_paths"):
        op.drop_column("task_packets", "allowed_paths")
