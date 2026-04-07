"""ScannerPolicyStore table — stores scanner-generated policies per project per source."""

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base


class ScannerPolicyRow(Base):
    __tablename__ = "scanner_policy_store"
    __table_args__ = (
        UniqueConstraint("project_id", "source", "policy_type", name="uq_scanner_policy"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)   # "mass", "snyk", "sonarqube"
    scan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "cedar", "bedrock", etc.
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
