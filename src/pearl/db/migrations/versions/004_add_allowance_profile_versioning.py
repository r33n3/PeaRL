"""Add allowance profile versioning fields.

Revision ID: 004_add_allowance_profile_versioning
Revises: 003
Create Date: 2026-04-02

"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003_add_trust_accumulation"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade() -> None:
    if not _column_exists("allowance_profiles", "profile_version"):
        op.add_column(
            "allowance_profiles",
            sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        )
    if not _column_exists("task_packets", "allowance_profile_id"):
        op.add_column(
            "task_packets",
            sa.Column("allowance_profile_id", sa.String(128), nullable=True),
        )
    if not _column_exists("task_packets", "allowance_profile_version"):
        op.add_column(
            "task_packets",
            sa.Column("allowance_profile_version", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("task_packets", "allowance_profile_version")
    op.drop_column("task_packets", "allowance_profile_id")
    op.drop_column("allowance_profiles", "profile_version")
