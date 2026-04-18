"""Capture lifespan ALTER TABLE blocks as idempotent migration.

Revision ID: 005
Revises: 004
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    cols = [c["name"] for c in inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    # 1. org_baselines.bu_id VARCHAR(128) with FK to business_units
    if _table_exists("org_baselines") and not _column_exists("org_baselines", "bu_id"):
        op.add_column(
            "org_baselines",
            sa.Column("bu_id", sa.String(128), sa.ForeignKey("business_units.bu_id"), nullable=True),
        )

    # 2. integration_endpoints.project_id — make nullable (PostgreSQL only)
    if _table_exists("integration_endpoints") and _column_exists("integration_endpoints", "project_id"):
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            op.alter_column("integration_endpoints", "project_id", nullable=True)

    # 3. projects.claude_md_verified BOOLEAN NOT NULL DEFAULT FALSE
    if _table_exists("projects") and not _column_exists("projects", "claude_md_verified"):
        op.add_column(
            "projects",
            sa.Column("claude_md_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # 4. exception_records.exception_type VARCHAR(20) NOT NULL DEFAULT 'exception'
    if _table_exists("exception_records") and not _column_exists("exception_records", "exception_type"):
        op.add_column(
            "exception_records",
            sa.Column(
                "exception_type",
                sa.String(20),
                nullable=False,
                server_default=sa.text("'exception'"),
            ),
        )

    # 5. exception_records.title VARCHAR(256) nullable
    if _table_exists("exception_records") and not _column_exists("exception_records", "title"):
        op.add_column(
            "exception_records",
            sa.Column("title", sa.String(256), nullable=True),
        )

    # 6. exception_records.risk_rating VARCHAR(20) nullable
    if _table_exists("exception_records") and not _column_exists("exception_records", "risk_rating"):
        op.add_column(
            "exception_records",
            sa.Column("risk_rating", sa.String(20), nullable=True),
        )

    # 7. exception_records.remediation_plan TEXT nullable
    if _table_exists("exception_records") and not _column_exists("exception_records", "remediation_plan"):
        op.add_column(
            "exception_records",
            sa.Column("remediation_plan", sa.Text(), nullable=True),
        )

    # 8. exception_records.board_briefing TEXT nullable
    if _table_exists("exception_records") and not _column_exists("exception_records", "board_briefing"):
        op.add_column(
            "exception_records",
            sa.Column("board_briefing", sa.Text(), nullable=True),
        )

    # 9. exception_records.finding_ids JSONB nullable
    if _table_exists("exception_records") and not _column_exists("exception_records", "finding_ids"):
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            col_type = postgresql.JSONB()
        else:
            col_type = sa.JSON()
        op.add_column(
            "exception_records",
            sa.Column("finding_ids", col_type, nullable=True),
        )

    # 10. projects.tags JSONB nullable
    if _table_exists("projects") and not _column_exists("projects", "tags"):
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            col_type = postgresql.JSONB()
        else:
            col_type = sa.JSON()
        op.add_column(
            "projects",
            sa.Column("tags", col_type, nullable=True),
        )


def downgrade() -> None:
    # Reverse in reverse order

    # 10. projects.tags
    if _table_exists("projects") and _column_exists("projects", "tags"):
        op.drop_column("projects", "tags")

    # 9. exception_records.finding_ids
    if _table_exists("exception_records") and _column_exists("exception_records", "finding_ids"):
        op.drop_column("exception_records", "finding_ids")

    # 8. exception_records.board_briefing
    if _table_exists("exception_records") and _column_exists("exception_records", "board_briefing"):
        op.drop_column("exception_records", "board_briefing")

    # 7. exception_records.remediation_plan
    if _table_exists("exception_records") and _column_exists("exception_records", "remediation_plan"):
        op.drop_column("exception_records", "remediation_plan")

    # 6. exception_records.risk_rating
    if _table_exists("exception_records") and _column_exists("exception_records", "risk_rating"):
        op.drop_column("exception_records", "risk_rating")

    # 5. exception_records.title
    if _table_exists("exception_records") and _column_exists("exception_records", "title"):
        op.drop_column("exception_records", "title")

    # 4. exception_records.exception_type
    if _table_exists("exception_records") and _column_exists("exception_records", "exception_type"):
        op.drop_column("exception_records", "exception_type")

    # 3. projects.claude_md_verified
    if _table_exists("projects") and _column_exists("projects", "claude_md_verified"):
        op.drop_column("projects", "claude_md_verified")

    # 2. integration_endpoints.project_id — restore NOT NULL (PostgreSQL only)
    if _table_exists("integration_endpoints") and _column_exists("integration_endpoints", "project_id"):
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            op.alter_column("integration_endpoints", "project_id", nullable=False)

    # 1. org_baselines.bu_id
    if _table_exists("org_baselines") and _column_exists("org_baselines", "bu_id"):
        op.drop_column("org_baselines", "bu_id")
