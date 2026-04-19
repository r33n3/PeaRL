"""Add governance container fields to projects table.

Revision ID: 009
Revises: 007
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op


revision = "009"
down_revision = "007"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    cols = [
        ("intake_card_id", sa.String(256)),
        ("goal_id", sa.String(256)),
        ("target_type", sa.String(128)),
        ("target_id", sa.String(512)),
        ("risk_classification", sa.String(64)),
        ("agent_members", sa.JSON),
        ("litellm_key_refs", sa.JSON),
        ("memory_policy_refs", sa.JSON),
        ("qualification_packet_id", sa.String(256)),
    ]
    for col_name, col_type in cols:
        if not _column_exists("projects", col_name):
            op.add_column("projects", sa.Column(col_name, col_type, nullable=True))


def downgrade():
    for col_name in [
        "intake_card_id",
        "goal_id",
        "target_type",
        "target_id",
        "risk_classification",
        "agent_members",
        "litellm_key_refs",
        "memory_policy_refs",
        "qualification_packet_id",
    ]:
        if _column_exists("projects", col_name):
            op.drop_column("projects", col_name)
