"""Business Unit table — Org → BU → Project hierarchy."""

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class BusinessUnitRow(Base, TimestampMixin):
    __tablename__ = "business_units"

    bu_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("orgs.org_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    framework_selections: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    additional_guardrails: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
