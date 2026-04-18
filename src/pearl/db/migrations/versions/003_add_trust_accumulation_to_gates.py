"""Add trust accumulation fields to promotion_gates.

Revision ID: 003_add_trust_accumulation
Revises: 002
Create Date: 2026-03-31

"""

from alembic import op
import sqlalchemy as sa

revision = "003_add_trust_accumulation"
down_revision = "002"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists("promotion_gates", "auto_pass"):
        op.add_column(
            "promotion_gates",
            sa.Column("auto_pass", sa.Boolean(), nullable=False, server_default="0"),
        )
    if not _column_exists("promotion_gates", "pass_count"):
        op.add_column(
            "promotion_gates",
            sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _column_exists("promotion_gates", "auto_pass_threshold"):
        op.add_column(
            "promotion_gates",
            sa.Column("auto_pass_threshold", sa.Integer(), nullable=False, server_default="5"),
        )


def downgrade() -> None:
    op.drop_column("promotion_gates", "auto_pass_threshold")
    op.drop_column("promotion_gates", "pass_count")
    op.drop_column("promotion_gates", "auto_pass")
