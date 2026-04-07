"""Add scanner_policy_store table.

Revision ID: 006
Revises: 004
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "004"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists("scanner_policy_store"):
        return
    op.create_table(
        "scanner_policy_store",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), sa.ForeignKey("projects.project_id"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("scan_id", sa.String(128), nullable=False),
        sa.Column("policy_type", sa.String(50), nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "source", "policy_type", name="uq_scanner_policy"),
    )


def downgrade() -> None:
    op.drop_table("scanner_policy_store")
