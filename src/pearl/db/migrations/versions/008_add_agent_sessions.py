"""Add agent_sessions table.

Revision ID: 008
Revises: 007
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("agent_sessions"):
        return
    op.create_table(
        "agent_sessions",
        sa.Column("agent_session_id", sa.String(64), primary_key=True),
        sa.Column("definition_id", sa.String(64), sa.ForeignKey("agent_definitions.agent_definition_id"), nullable=False, index=True),
        sa.Column("project_id", sa.String(128), sa.ForeignKey("projects.project_id"), nullable=False, index=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_session_id", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_sessions")
