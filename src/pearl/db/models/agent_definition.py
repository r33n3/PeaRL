"""AgentDefinitionRow — tracks agent YAML/JSON definitions submitted for assessment."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pearl.db.base import Base


class AgentDefinitionRow(Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("project_id", "git_ref", "git_path", "environment", name="uq_agent_definition"),
    )
    agent_definition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    git_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    git_path: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_assessment")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
