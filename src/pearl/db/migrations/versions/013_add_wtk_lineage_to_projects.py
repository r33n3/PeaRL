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


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    cols = [
        ("wtk_package_id", sa.String(256)),
        ("factory_run_id", sa.String(256)),
        ("build_system", sa.String(128)),
    ]
    for col_name, col_type in cols:
        if not _column_exists("projects", col_name):
            op.add_column("projects", sa.Column(col_name, col_type, nullable=True))


def downgrade():
    for col_name in [
        "wtk_package_id",
        "factory_run_id",
        "build_system",
    ]:
        if _column_exists("projects", col_name):
            op.drop_column("projects", col_name)
