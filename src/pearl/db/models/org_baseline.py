"""OrgBaseline table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class OrgBaselineRow(Base, TimestampMixin):
    __tablename__ = "org_baselines"

    baseline_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    org_name: Mapped[str] = mapped_column(String(200), nullable=False)
    defaults: Mapped[dict] = mapped_column(JSON, nullable=False)
    environment_defaults: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    integrity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
