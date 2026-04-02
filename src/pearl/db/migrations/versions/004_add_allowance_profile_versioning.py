"""Add allowance profile versioning fields.

Revision ID: 004_add_allowance_profile_versioning
Revises: 003
Create Date: 2026-04-02

"""

from alembic import op
import sqlalchemy as sa

revision = "004_add_allowance_profile_versioning"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "allowance_profiles",
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "task_packets",
        sa.Column("allowance_profile_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "task_packets",
        sa.Column("allowance_profile_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_packets", "allowance_profile_version")
    op.drop_column("task_packets", "allowance_profile_id")
    op.drop_column("allowance_profiles", "profile_version")
