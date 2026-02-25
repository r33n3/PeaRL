"""ApplicationSpec table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class AppSpecRow(Base, TimestampMixin):
    __tablename__ = "app_specs"

    app_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    full_spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    integrity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
