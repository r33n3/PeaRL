"""AgentCore CloudWatch scan state — watermark and baseline metrics per org."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class AgentCoreScanStateRow(Base, TimestampMixin):
    """Persists polling state for the CloudWatch → PeaRL finding bridge.

    One row per org. The ``log_watermark`` is the timestamp of the last
    CloudWatch log entry successfully processed — the next scan starts
    from here, avoiding re-processing of already-seen entries.

    ``baseline_call_rate`` is a rolling average (calls/minute) used to
    detect volume anomalies (CWD-005): a spike beyond
    ``cloudwatch_volume_anomaly_threshold`` standard deviations triggers
    a MODERATE finding.
    """

    __tablename__ = "agentcore_scan_states"

    state_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    # Watermark: next scan window starts from here
    log_watermark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Last scan job reference
    last_scan_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_scan_findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scan_entries_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Rolling baseline for volume anomaly detection (CWD-005)
    baseline_call_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
