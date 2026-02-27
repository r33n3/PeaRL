"""Project table."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ProjectRow(Base, TimestampMixin):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_team: Mapped[str] = mapped_column(String(200), nullable=False)
    business_criticality: Mapped[str] = mapped_column(String(50), nullable=False)
    external_exposure: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
    org_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    bu_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("business_units.bu_id"), nullable=True, index=True
    )
