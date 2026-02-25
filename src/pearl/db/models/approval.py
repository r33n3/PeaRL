"""Approval tables."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ApprovalRequestRow(Base, TimestampMixin):
    __tablename__ = "approval_requests"

    approval_request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    request_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalDecisionRow(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_request_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("approval_requests.approval_request_id"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(200), nullable=False)
    decider_role: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    conditions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
