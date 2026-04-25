"""Add WTK factory lineage fields to projects table.

Revision ID: 013
Revises: 012
Create Date: 2026-04-25
"""
import sqlalchemy as sa
from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("wtk_package_id", sa.String(256), nullable=True))
    op.add_column("projects", sa.Column("factory_run_id", sa.String(256), nullable=True))
    op.add_column("projects", sa.Column("build_system", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "build_system")
    op.drop_column("projects", "factory_run_id")
    op.drop_column("projects", "wtk_package_id")
