"""AgentCore CloudWatch decision log parser.

Analyses raw CloudWatch log entries emitted by AgentCore Cedar policy
evaluations and produces PeaRL findings for five detection types:

  CWD-001  Policy hash drift — logged policyHash ≠ PeaRL's active bundle
  CWD-002  Decision drift — principal+action pair flipped DENY → ALLOW
  CWD-003  Agent sprawl — principalId not in any PeaRL-registered alias
  CWD-004  Governance bypass — ALLOW for an action the Cedar bundle forbids
  CWD-005  Volume anomaly — call rate spike beyond N std devs from baseline
"""
from __future__ import annotations

import structlog
import math
from datetime import datetime, timezone
from typing import NamedTuple

logger = structlog.get_logger(__name__)

# ── Finding severity map per detection code ────────────────────────────────────
_SEVERITY: dict[str, str] = {
    "CWD-001": "critical",   # Policy tampered outside governance workflow
    "CWD-002": "high",       # Runtime behaviour changed unexpectedly
    "CWD-003": "high",       # Unregistered agent operating in production
    "CWD-004": "critical",   # Active Cedar forbid clause circumvented
    "CWD-005": "moderate",   # Unusual call volume — possible misuse
}


class AnalysisInput(NamedTuple):
    log_entries: list[dict]
    active_bundle_hash: str | None
    registered_alias_ids: set[str]
    forbidden_actions: set[str]   # actions the current Cedar bundle forbids
    baseline_call_rate: float | None
    anomaly_threshold: float       # std devs (e.g. 3.0)
    org_id: str
    project_id: str | None
    environment: str


class DetectedFinding(NamedTuple):
    anomaly_code: str
    title: str
    severity: str
    details: dict


def analyse(inp: AnalysisInput) -> list[DetectedFinding]:
    """Return a list of findings derived from the log entries."""
    findings: list[DetectedFinding] = []

    if not inp.log_entries:
        return findings

    findings.extend(_detect_hash_drift(inp))
    findings.extend(_detect_decision_drift(inp))
    findings.extend(_detect_agent_sprawl(inp))
    findings.extend(_detect_governance_bypass(inp))
    volume_finding = _detect_volume_anomaly(inp)
    if volume_finding:
        findings.append(volume_finding)

    return findings


# ── Detection functions ────────────────────────────────────────────────────────

def _detect_hash_drift(inp: AnalysisInput) -> list[DetectedFinding]:
    """CWD-001: policyHash in log ≠ active bundle hash."""
    if not inp.active_bundle_hash:
        return []

    drift_hashes: set[str] = set()
    for entry in inp.log_entries:
        logged_hash = entry.get("policyHash", "")
        if logged_hash and logged_hash != inp.active_bundle_hash:
            drift_hashes.add(logged_hash)

    if not drift_hashes:
        return []

    return [DetectedFinding(
        anomaly_code="CWD-001",
        severity=_SEVERITY["CWD-001"],
        title="Cedar policy hash drift detected (CWD-001)",
        details={
            "expected_hash": inp.active_bundle_hash,
            "observed_hashes": sorted(drift_hashes),
            "affected_entries": sum(
                1 for e in inp.log_entries
                if e.get("policyHash") and e["policyHash"] != inp.active_bundle_hash
            ),
        },
    )]


def _detect_decision_drift(inp: AnalysisInput) -> list[DetectedFinding]:
    """CWD-002: same (principal, action) pair produces ALLOW after prior DENY.

    Uses a simple within-window analysis: if we see both DENY and ALLOW for
    the same principal+action in the same scan window, flag it as drift.  A
    production implementation would compare against the previous scan window.
    """
    pair_decisions: dict[str, set[str]] = {}
    for entry in inp.log_entries:
        principal = entry.get("principalId", "")
        action = entry.get("action", "")
        decision = (entry.get("decision") or "").upper()
        if not (principal and action and decision):
            continue
        key = f"{principal}|{action}"
        pair_decisions.setdefault(key, set()).add(decision)

    drifted = [
        k for k, decisions in pair_decisions.items()
        if "ALLOW" in decisions and "DENY" in decisions
    ]

    if not drifted:
        return []

    return [DetectedFinding(
        anomaly_code="CWD-002",
        severity=_SEVERITY["CWD-002"],
        title=f"Cedar decision drift on {len(drifted)} principal/action pair(s) (CWD-002)",
        details={
            "drifted_pairs": sorted(drifted)[:20],  # cap at 20 for readability
            "total_drifted": len(drifted),
        },
    )]


def _detect_agent_sprawl(inp: AnalysisInput) -> list[DetectedFinding]:
    """CWD-003: principalId in logs not in PeaRL-registered aliases."""
    if not inp.registered_alias_ids:
        # If no aliases registered yet, skip to avoid false positives on initial setup
        return []

    unknown: set[str] = set()
    for entry in inp.log_entries:
        principal = entry.get("principalId", "")
        if principal and principal not in inp.registered_alias_ids:
            unknown.add(principal)

    if not unknown:
        return []

    return [DetectedFinding(
        anomaly_code="CWD-003",
        severity=_SEVERITY["CWD-003"],
        title=f"{len(unknown)} unregistered agent alias(es) detected (CWD-003)",
        details={
            "unregistered_principals": sorted(unknown)[:20],
            "total_unregistered": len(unknown),
        },
    )]


def _detect_governance_bypass(inp: AnalysisInput) -> list[DetectedFinding]:
    """CWD-004: ALLOW decision for an action the current Cedar bundle forbids."""
    if not inp.forbidden_actions:
        return []

    bypass_entries: list[dict] = []
    for entry in inp.log_entries:
        action = entry.get("action", "")
        decision = (entry.get("decision") or "").upper()
        # Strip namespace prefix for matching (e.g. "AgentCore::Action::Execute" → "Execute")
        action_short = action.rsplit("::", 1)[-1]
        if decision == "ALLOW" and (action in inp.forbidden_actions or action_short in inp.forbidden_actions):
            bypass_entries.append({
                "principalId": entry.get("principalId"),
                "action": action,
                "resource": entry.get("resource"),
                "timestamp": entry.get("@timestamp"),
            })

    if not bypass_entries:
        return []

    return [DetectedFinding(
        anomaly_code="CWD-004",
        severity=_SEVERITY["CWD-004"],
        title=f"Governance bypass: {len(bypass_entries)} forbidden action(s) allowed (CWD-004)",
        details={
            "bypass_events": bypass_entries[:20],
            "total_bypass_events": len(bypass_entries),
        },
    )]


def _detect_volume_anomaly(inp: AnalysisInput) -> DetectedFinding | None:
    """CWD-005: call rate spike > baseline_call_rate + N * σ.

    Uses the scan window entry count as a proxy for call rate.  A proper
    implementation would track per-minute buckets.
    """
    if inp.baseline_call_rate is None or inp.baseline_call_rate <= 0:
        return None

    # Treat the number of entries in this scan as the observed rate proxy
    observed_rate = float(len(inp.log_entries))
    # Approximate σ using Poisson assumption: σ ≈ sqrt(baseline)
    sigma = math.sqrt(inp.baseline_call_rate) if inp.baseline_call_rate > 0 else 1.0
    threshold_rate = inp.baseline_call_rate + inp.anomaly_threshold * sigma

    if observed_rate <= threshold_rate:
        return None

    z_score = (observed_rate - inp.baseline_call_rate) / sigma

    return DetectedFinding(
        anomaly_code="CWD-005",
        severity=_SEVERITY["CWD-005"],
        title=f"AgentCore call volume anomaly: {observed_rate:.0f} events (z={z_score:.1f}σ) (CWD-005)",
        details={
            "observed_entries": len(inp.log_entries),
            "baseline_call_rate": inp.baseline_call_rate,
            "threshold_rate": threshold_rate,
            "z_score": round(z_score, 2),
            "anomaly_threshold_sigmas": inp.anomaly_threshold,
        },
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def extract_registered_aliases(bundle_snapshot: dict | None) -> set[str]:
    """Pull alias IDs from a Cedar bundle snapshot (from CedarDeploymentRow)."""
    if not bundle_snapshot:
        return set()
    static: dict = bundle_snapshot.get("policies", {}).get("static", {})
    aliases: set[str] = set()
    for policy_id in static:
        # Policy IDs of the form: pearl_permit_alias_<alias_id>_<env>
        if policy_id.startswith("pearl_permit_alias_"):
            parts = policy_id[len("pearl_permit_alias_"):].rsplit("_", 1)
            if parts:
                aliases.add(parts[0])
    return aliases


def extract_forbidden_actions(bundle_snapshot: dict | None) -> set[str]:
    """Extract action names targeted by forbid policies in the bundle snapshot."""
    if not bundle_snapshot:
        return set()
    static: dict = bundle_snapshot.get("policies", {}).get("static", {})
    forbidden: set[str] = set()
    for policy_id, policy in static.items():
        if not policy_id.startswith("pearl_forbid_"):
            continue
        statement: str = policy.get("statement", "")
        # Simple extraction: look for action == AgentCore::Action::"<Name>"
        import re
        for match in re.finditer(r'action\s*==\s*\S+::"(\w+)"', statement):
            forbidden.add(match.group(1))
    return forbidden


def watermark_from_entries(entries: list[dict]) -> datetime | None:
    """Return the timestamp of the last entry, used as the next scan watermark."""
    if not entries:
        return None
    timestamps = []
    for e in entries:
        ts_str = e.get("@timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            timestamps.append(ts)
        except ValueError:
            continue
    return max(timestamps) if timestamps else None
