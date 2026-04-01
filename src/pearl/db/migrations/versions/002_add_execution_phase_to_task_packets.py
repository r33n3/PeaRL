"""Add execution_phase and phase_history columns to task_packets table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-31 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add execution_phase column with default 'planning'
    op.add_column(
        "task_packets",
        sa.Column(
            "execution_phase",
            sa.String(50),
            nullable=False,
            server_default="planning",
        ),
    )

    # Add phase_history column as JSON (TEXT in SQLite) with default empty array
    op.add_column(
        "task_packets",
        sa.Column(
            "phase_history",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    # Drop phase_history column
    op.drop_column("task_packets", "phase_history")

    # Drop execution_phase column
    op.drop_column("task_packets", "execution_phase")
