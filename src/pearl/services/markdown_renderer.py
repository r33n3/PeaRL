"""Markdown rendering service for PeaRL governance data.

Renders project summaries, promotion evaluations, findings, and fairness
posture as human-readable markdown for Claude Desktop and dashboards.
"""

from __future__ import annotations

from datetime import datetime


def render_project_summary(
    project: dict,
    findings_by_severity: dict[str, int] | None = None,
    promotion: dict | None = None,
    fairness: dict | None = None,
    environment: str | None = None,
) -> str:
    """Render a full project governance summary in markdown."""
    lines: list[str] = []
    lines.append(f"# {project.get('name', project.get('project_id', 'Unknown'))}")
    lines.append("")

    # Project identity
    lines.append("## Project Identity")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Project ID | `{project.get('project_id', 'N/A')}` |")
    lines.append(f"| Owner | {project.get('owner_team', 'N/A')} |")
    lines.append(f"| Criticality | {project.get('business_criticality', 'N/A')} |")
    lines.append(f"| External Exposure | {project.get('external_exposure', 'N/A')} |")
    lines.append(f"| AI-Enabled | {'Yes' if project.get('ai_enabled') else 'No'} |")
    if environment:
        lines.append(f"| Environment | {environment} |")
    lines.append("")

    # Findings summary
    if findings_by_severity:
        lines.append("## Findings Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in ("critical", "high", "moderate", "low", "informational"):
            count = findings_by_severity.get(sev, 0)
            if count > 0:
                lines.append(f"| {sev.capitalize()} | **{count}** |")
            else:
                lines.append(f"| {sev.capitalize()} | {count} |")
        total = sum(findings_by_severity.values())
        lines.append(f"| **Total** | **{total}** |")
        lines.append("")

    # Promotion readiness
    if promotion:
        lines.append(render_promotion_evaluation(promotion))

    # Fairness posture
    if fairness:
        lines.append(render_fairness_posture(fairness))

    return "\n".join(lines)


def render_promotion_evaluation(evaluation: dict) -> str:
    """Render promotion gate evaluation results as markdown."""
    lines: list[str] = []

    src = evaluation.get("source_environment", evaluation.get("current_environment", "?"))
    tgt = evaluation.get("target_environment", evaluation.get("next_environment", "?"))
    status = evaluation.get("status", "unknown")
    passed = evaluation.get("passed_count", 0)
    total = evaluation.get("total_count", 0)
    pct = evaluation.get("progress_pct", 0)

    status_icon = "PASS" if status == "passed" else "BLOCKED" if status == "failed" else status.upper()

    lines.append(f"## Promotion Readiness: {src} → {tgt}")
    lines.append("")
    lines.append(f"**Status:** {status_icon} — {passed}/{total} rules passing ({pct}%)")
    lines.append("")

    # Rule results table
    rule_results = evaluation.get("rule_results", [])
    if rule_results:
        passing = [r for r in rule_results if r.get("result") == "passed"]
        failing = [r for r in rule_results if r.get("result") != "passed"]

        if failing:
            lines.append("### Blocking")
            lines.append("")
            for r in failing:
                msg = r.get("message", r.get("description", ""))
                exc = f" _(exception: `{r['exception_id']}`)_" if r.get("exception_id") else ""
                lines.append(f"- **{r.get('rule_type', '?')}** — {msg}{exc}")
            lines.append("")

        if passing:
            lines.append("### Passing")
            lines.append("")
            for r in passing:
                msg = r.get("message", r.get("description", ""))
                lines.append(f"- `{r.get('rule_type', '?')}` — {msg}")
            lines.append("")

    # Blockers summary
    blockers = evaluation.get("blockers", [])
    if blockers:
        lines.append("### Blockers")
        lines.append("")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    evaluated_at = evaluation.get("evaluated_at") or evaluation.get("last_evaluated_at")
    if evaluated_at:
        lines.append(f"_Last evaluated: {evaluated_at}_")
        lines.append("")

    return "\n".join(lines)


def render_findings_list(findings: list[dict]) -> str:
    """Render a list of findings as a markdown table."""
    lines: list[str] = []
    lines.append("## Findings")
    lines.append("")

    if not findings:
        lines.append("No findings recorded.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| ID | Severity | Category | Title | Status |")
    lines.append("|----|----------|----------|-------|--------|")

    for f in findings:
        fid = f.get("finding_id", "?")
        sev = f.get("severity", "?")
        cat = f.get("category", "?")
        title = f.get("title", "?")
        status = f.get("status", "open")
        cvss = f.get("cvss_score")
        cvss_str = f" (CVSS {cvss})" if cvss is not None else ""
        lines.append(f"| `{fid}` | {sev}{cvss_str} | {cat} | {title} | {status} |")

    lines.append("")
    return "\n".join(lines)


def render_release_readiness(
    project_id: str,
    environment: str,
    findings_by_severity: dict[str, int],
    approval_blockers: list[str],
    promotion: dict | None = None,
    fairness: dict | None = None,
) -> str:
    """Render a release readiness report as markdown."""
    lines: list[str] = []
    lines.append(f"# Release Readiness Report: {project_id}")
    lines.append("")
    lines.append(f"**Environment:** {environment}")
    lines.append("")

    # Findings counts
    total_findings = sum(findings_by_severity.values())
    critical = findings_by_severity.get("critical", 0)
    high = findings_by_severity.get("high", 0)

    ready = critical == 0 and high == 0 and len(approval_blockers) == 0

    lines.append(f"**Overall Status:** {'READY' if ready else 'NOT READY'}")
    lines.append("")

    lines.append("## Security Findings")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in ("critical", "high", "moderate", "low", "informational"):
        count = findings_by_severity.get(sev, 0)
        lines.append(f"| {sev.capitalize()} | {count} |")
    lines.append(f"| **Total** | **{total_findings}** |")
    lines.append("")

    if approval_blockers:
        lines.append("## Approval Blockers")
        lines.append("")
        for b in approval_blockers:
            lines.append(f"- {b}")
        lines.append("")

    if promotion:
        lines.append(render_promotion_evaluation(promotion))

    if fairness:
        lines.append(render_fairness_posture(fairness))

    return "\n".join(lines)


def render_fairness_posture(fairness: dict) -> str:
    """Render fairness governance posture as markdown."""
    lines: list[str] = []
    lines.append("## Fairness Governance")
    lines.append("")

    fc = fairness.get("fairness_case")
    if fc:
        lines.append(f"**Fairness Case:** `{fc.get('fc_id', 'N/A')}`")
        lines.append(f"- Risk Tier: {fc.get('risk_tier', 'N/A')}")
        lines.append(f"- Criticality: {fc.get('fairness_criticality', 'N/A')}")
        lines.append("")

    requirements = fairness.get("requirements", [])
    if requirements:
        lines.append("### Requirements")
        lines.append("")
        lines.append("| Requirement | Type | Gate Mode | Status |")
        lines.append("|-------------|------|-----------|--------|")
        for req in requirements:
            stmt = req.get("statement", "?")
            rtype = req.get("type", "?")
            gmode = req.get("gate_mode", "?")
            status = req.get("status", "pending")
            lines.append(f"| {stmt} | {rtype} | {gmode} | {status} |")
        lines.append("")

    evidence = fairness.get("evidence")
    if evidence:
        att_status = evidence.get("attestation_status", "unsigned")
        lines.append(f"### Evidence")
        lines.append(f"- Evidence ID: `{evidence.get('evidence_id', 'N/A')}`")
        lines.append(f"- Attestation: **{att_status}**")
        lines.append("")

    signals = fairness.get("monitoring_signals", [])
    if signals:
        lines.append("### Monitoring Signals")
        lines.append("")
        lines.append("| Signal | Value | Threshold | Status |")
        lines.append("|--------|-------|-----------|--------|")
        for s in signals:
            stype = s.get("signal_type", "?")
            val = s.get("value", "?")
            thresh = s.get("threshold", "N/A")
            ok = "OK" if s.get("within_threshold", True) else "ALERT"
            lines.append(f"| {stype} | {val} | {thresh} | {ok} |")
        lines.append("")

    exceptions = fairness.get("exceptions", [])
    if exceptions:
        lines.append("### Active Exceptions")
        lines.append("")
        for exc in exceptions:
            lines.append(f"- `{exc.get('exception_id', '?')}` — {exc.get('reason', 'N/A')} (status: {exc.get('status', '?')})")
        lines.append("")

    return "\n".join(lines)
