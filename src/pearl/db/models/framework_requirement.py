"""Framework Requirement table — derived requirements from BU framework selections."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class FrameworkRequirementRow(Base, TimestampMixin):
    __tablename__ = "framework_requirements"

    requirement_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    bu_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("business_units.bu_id"), nullable=False, index=True
    )
    framework: Mapped[str] = mapped_column(String(100), nullable=False)
    control_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # List of transition strings like ["sandbox->dev", "dev->preprod"] or ["*"]
    applies_to_transitions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requirement_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mandatory"
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False, default="attestation")
