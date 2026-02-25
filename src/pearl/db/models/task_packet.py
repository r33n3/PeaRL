"""TaskPacket table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class TaskPacketRow(Base, TimestampMixin):
    __tablename__ = "task_packets"

    task_packet_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    packet_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
