"""Add agent_definitions table.

Revision ID: 007
Revises: 006
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("agent_definitions"):
        return
    op.create_table(
        "agent_definitions",
        sa.Column("agent_definition_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), sa.ForeignKey("projects.project_id"), nullable=False, index=True),
        sa.Column("git_ref", sa.String(64), nullable=False),
        sa.Column("git_path", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_agent_id", sa.String(128), nullable=True),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_assessment"),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "git_ref", "git_path", "environment", name="uq_agent_definition"),
    )


def downgrade() -> None:
    op.drop_table("agent_definitions")
