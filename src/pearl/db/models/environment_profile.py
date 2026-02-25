"""EnvironmentProfile table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class EnvironmentProfileRow(Base, TimestampMixin):
    __tablename__ = "environment_profiles"

    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    delivery_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    autonomy_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    integrity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
