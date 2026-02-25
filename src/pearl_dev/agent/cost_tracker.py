"""Governance cost tracking — records and queries Agent SDK spend.

Every pearl-agent workflow appends to .pearl/cost-ledger.jsonl with:
- workflow type (scan, promote, review, onboard, custom)
- cost in USD
- model used
- tools called
- duration
- timestamp

This makes the hidden cost of security governance visible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CostEntry:
    """Single workflow cost record."""

    timestamp: str
    project_id: str
    environment: str
    workflow: str
    model: str
    cost_usd: float
    duration_ms: int | None
    num_turns: int
    tools_called: list[str]
    tool_count: int
    success: bool
    session_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CostTracker:
    """Persists and queries governance cost data."""

    def __init__(self, project_root: Path) -> None:
        self._ledger_path = project_root / ".pearl" / "cost-ledger.jsonl"

    def record(self, entry: CostEntry) -> None:
        """Append a cost entry to the ledger."""
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def load_all(self) -> list[CostEntry]:
        """Load all cost entries from the ledger."""
        if not self._ledger_path.exists():
            return []

        entries = []
        for line in self._ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(CostEntry(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    def summary(self) -> CostSummary:
        """Generate a cost summary from all ledger entries."""
        entries = self.load_all()
        return CostSummary.from_entries(entries)


@dataclass
class CostSummary:
    """Aggregated cost metrics for a project."""

    total_cost_usd: float
    total_runs: int
    total_tools_called: int
    total_duration_ms: int
    by_workflow: dict[str, WorkflowCostBreakdown]
    by_model: dict[str, float]
    first_run: str | None
    last_run: str | None

    @classmethod
    def from_entries(cls, entries: list[CostEntry]) -> CostSummary:
        total_cost = 0.0
        total_tools = 0
        total_duration = 0
        by_workflow: dict[str, list[CostEntry]] = {}
        by_model: dict[str, float] = {}

        for e in entries:
            total_cost += e.cost_usd
            total_tools += e.tool_count
            total_duration += e.duration_ms or 0

            by_workflow.setdefault(e.workflow, []).append(e)
            by_model[e.model] = by_model.get(e.model, 0.0) + e.cost_usd

        workflow_breakdowns = {}
        for wf, wf_entries in by_workflow.items():
            workflow_breakdowns[wf] = WorkflowCostBreakdown(
                workflow=wf,
                runs=len(wf_entries),
                total_cost_usd=sum(e.cost_usd for e in wf_entries),
                avg_cost_usd=sum(e.cost_usd for e in wf_entries) / len(wf_entries),
                avg_tools_per_run=sum(e.tool_count for e in wf_entries) / len(wf_entries),
                avg_duration_ms=sum(e.duration_ms or 0 for e in wf_entries) / len(wf_entries),
                success_rate=sum(1 for e in wf_entries if e.success) / len(wf_entries),
            )

        return cls(
            total_cost_usd=total_cost,
            total_runs=len(entries),
            total_tools_called=total_tools,
            total_duration_ms=total_duration,
            by_workflow=workflow_breakdowns,
            by_model=by_model,
            first_run=entries[0].timestamp if entries else None,
            last_run=entries[-1].timestamp if entries else None,
        )

    def format_report(self) -> str:
        """Format a human-readable cost report."""
        if self.total_runs == 0:
            return "No governance workflows have been run yet."

        lines = [
            "PeaRL Governance Cost Report",
            "=" * 40,
            f"Total cost:       ${self.total_cost_usd:.4f}",
            f"Total runs:       {self.total_runs}",
            f"Total tools used: {self.total_tools_called}",
            f"Total time:       {self.total_duration_ms / 1000:.1f}s",
            f"Avg cost/run:     ${self.total_cost_usd / self.total_runs:.4f}",
            f"Period:           {self._short_date(self.first_run)} to {self._short_date(self.last_run)}",
            "",
            "Cost by Workflow",
            "-" * 40,
        ]

        for wf, bd in sorted(self.by_workflow.items(), key=lambda x: x[1].total_cost_usd, reverse=True):
            lines.append(
                f"  {wf:<12} {bd.runs:>3} runs  "
                f"${bd.total_cost_usd:>8.4f}  "
                f"(avg ${bd.avg_cost_usd:.4f}/run, "
                f"{bd.avg_tools_per_run:.0f} tools, "
                f"{bd.avg_duration_ms / 1000:.0f}s, "
                f"{bd.success_rate * 100:.0f}% success)"
            )

        if len(self.by_model) > 1:
            lines.append("")
            lines.append("Cost by Model")
            lines.append("-" * 40)
            for model, cost in sorted(self.by_model.items(), key=lambda x: x[1], reverse=True):
                short_model = model.split("-")[1] if "-" in model else model
                pct = (cost / self.total_cost_usd * 100) if self.total_cost_usd > 0 else 0
                lines.append(f"  {short_model:<20} ${cost:>8.4f}  ({pct:.0f}%)")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for MCP tool response."""
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_runs": self.total_runs,
            "total_tools_called": self.total_tools_called,
            "total_duration_ms": self.total_duration_ms,
            "avg_cost_per_run_usd": round(self.total_cost_usd / max(self.total_runs, 1), 6),
            "period": {
                "first_run": self.first_run,
                "last_run": self.last_run,
            },
            "by_workflow": {
                wf: {
                    "runs": bd.runs,
                    "total_cost_usd": round(bd.total_cost_usd, 6),
                    "avg_cost_usd": round(bd.avg_cost_usd, 6),
                    "avg_tools_per_run": round(bd.avg_tools_per_run, 1),
                    "avg_duration_ms": round(bd.avg_duration_ms),
                    "success_rate": round(bd.success_rate, 2),
                }
                for wf, bd in self.by_workflow.items()
            },
            "by_model": {
                model: round(cost, 6)
                for model, cost in self.by_model.items()
            },
        }

    @staticmethod
    def _short_date(ts: str | None) -> str:
        if not ts:
            return "?"
        try:
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return ts[:10] if ts else "?"


@dataclass
class WorkflowCostBreakdown:
    """Cost breakdown for a single workflow type."""

    workflow: str
    runs: int
    total_cost_usd: float
    avg_cost_usd: float
    avg_tools_per_run: float
    avg_duration_ms: float
    success_rate: float
