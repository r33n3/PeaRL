"""CompiledPackage table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class CompiledPackageRow(Base, TimestampMixin):
    __tablename__ = "compiled_packages"

    package_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("projects.project_id"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    package_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    integrity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
