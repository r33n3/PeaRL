"""Org Environment Config table — per-org environment ladder definition."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class OrgEnvironmentConfigRow(Base, TimestampMixin):
    __tablename__ = "org_environment_configs"

    config_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("orgs.org_id"), nullable=False, unique=True, index=True
    )
    # List of EnvironmentStage dicts: {name, order, risk_level, requires_approval,
    #   approval_type, use_case_ref_required}
    stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
