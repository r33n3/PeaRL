"""Add factory_run_summaries table

Revision ID: 011
Revises: 010
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "factory_run_summaries",
        sa.Column("frun_id", sa.String(200), primary_key=True),
        sa.Column("project_id", sa.String(128), sa.ForeignKey("projects.project_id"), nullable=False, index=True),
        sa.Column("task_packet_id", sa.String(128), nullable=True),
        sa.Column("goal_id", sa.String(256), nullable=True),
        sa.Column("svid", sa.String(512), nullable=True),
        sa.Column("environment", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("models_used", sa.JSON, nullable=False, server_default="'[]'"),
        sa.Column("tools_called", sa.JSON, nullable=False, server_default="'[]'"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("anomaly_flags", sa.JSON, nullable=False, server_default="'[]'"),
        sa.Column("promoted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("promotion_env", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("outcome IN ('achieved', 'failed', 'abandoned')", name="ck_frun_outcome"),
    )
    op.create_index("ix_factory_run_summaries_task_packet_id", "factory_run_summaries", ["task_packet_id"])


def downgrade() -> None:
    op.drop_index("ix_factory_run_summaries_task_packet_id", table_name="factory_run_summaries")
    op.drop_table("factory_run_summaries")
