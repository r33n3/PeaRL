"""AgentSessionRow — tracks sessions created on agent platforms (Claude/OpenAI)."""
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from pearl.db.base import Base


class AgentSessionRow(Base):
    __tablename__ = "agent_sessions"
    agent_session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_definitions.agent_definition_id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
