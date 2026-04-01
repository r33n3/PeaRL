"""Workload table — maps active SPIRE SVIDs to task packets and allowance profiles."""

from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class WorkloadRow(Base, TimestampMixin):
    __tablename__ = "workloads"

    workload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    svid: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    task_packet_id: Mapped[str] = mapped_column(String(64), nullable=False)
    allowance_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(JSON, nullable=True)
