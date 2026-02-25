"""Notification storage table."""

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class NotificationRow(Base, TimestampMixin):
    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
