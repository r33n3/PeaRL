"""Add commit_sha, version_tag, branch to promotion_evaluations and promotion_history.

Revision ID: 001
Revises:
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promotion_evaluations", sa.Column("commit_sha", sa.String(200), nullable=True))
    op.add_column("promotion_evaluations", sa.Column("version_tag", sa.String(100), nullable=True))
    op.add_column("promotion_evaluations", sa.Column("branch", sa.String(200), nullable=True))

    op.add_column("promotion_history", sa.Column("commit_sha", sa.String(200), nullable=True))
    op.add_column("promotion_history", sa.Column("version_tag", sa.String(100), nullable=True))
    op.add_column("promotion_history", sa.Column("branch", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("promotion_evaluations", "branch")
    op.drop_column("promotion_evaluations", "version_tag")
    op.drop_column("promotion_evaluations", "commit_sha")

    op.drop_column("promotion_history", "branch")
    op.drop_column("promotion_history", "version_tag")
    op.drop_column("promotion_history", "commit_sha")
