"""Add signature column to audit_events table

Revision ID: 010
Revises: 009
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("signature", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_events", "signature")
