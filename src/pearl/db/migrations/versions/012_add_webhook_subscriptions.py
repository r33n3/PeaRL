"""Add webhook_subscriptions table

Revision ID: 012
Revises: 011
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("subscription_id", sa.String(128), primary_key=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(2048), nullable=False),
        sa.Column("event_types", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_subscriptions_active", "webhook_subscriptions", ["active"])


def downgrade() -> None:
    op.drop_index("ix_webhook_subscriptions_active", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")
