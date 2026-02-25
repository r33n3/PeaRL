"""Renders pearl-dev templates from compiled context package data."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from pearl.models.compiled_context import CompiledContextPackage

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_GOVERNANCE_BEGIN = "<!-- PEARL:GOVERNANCE:BEGIN -->"
_GOVERNANCE_END = "<!-- PEARL:GOVERNANCE:END -->"
_MARKER_PATTERN = re.compile(
    re.escape(_GOVERNANCE_BEGIN) + r".*?" + re.escape(_GOVERNANCE_END),
    re.DOTALL,
)


def _build_template_context(
    package: CompiledContextPackage,
    project_root: str = ".",
    promotion_readiness: dict | None = None,
    scan_targets: list[dict] | None = None,
) -> dict:
    """Extract template variables from a compiled context package."""
    pi = package.project_identity
    ap = package.autonomy_policy
    sr = package.security_requirements
    rt = package.required_tests

    required_tests: list[str] = []
    if rt:
        required_tests.extend(rt.security or [])
        required_tests.extend(rt.rai or [])
        required_tests.extend(rt.functional or [])

    approval_checkpoints = []
    for cp in package.approval_checkpoints or []:
        approval_checkpoints.append({
            "trigger": cp.trigger,
            "required_roles": cp.required_roles or [],
        })

    import os
    import sys
    # Use python.exe (works from both Windows and WSL via interop)
    # Fall back to full path only on non-Windows
    if os.name == "nt":
        python_exe = "python.exe"
    else:
        python_exe = sys.executable.replace("\\", "/")

    ctx: dict = {
        "project_id": pi.project_id,
        "environment": pi.environment,
        "autonomy_mode": ap.mode,
        "allowed_actions": sorted(ap.allowed_actions),
        "blocked_actions": sorted(ap.blocked_actions),
        "approval_required_for": sorted(ap.approval_required_for or []),
        "prohibited_patterns": sorted(sr.prohibited_patterns or []),
        "required_tests": required_tests,
        "approval_checkpoints": approval_checkpoints,
        "project_root": project_root.replace("\\", "/"),
        "python_executable": python_exe,
    }

    # Promotion readiness (from pearl-dev sync)
    if promotion_readiness:
        ctx["promotion"] = _build_promotion_context(promotion_readiness)

    # Fairness requirements (from compiled context or sync)
    fr = package.fairness_requirements
    if fr and isinstance(fr, dict):
        reqs = fr.get("requirements", [])
        if reqs:
            ctx["fairness_requirements"] = reqs

    # Scan targets (from pearl-dev sync)
    if scan_targets:
        ctx["scan_targets"] = scan_targets

    return ctx


def _build_promotion_context(readiness: dict) -> dict:
    """Transform promotion readiness API data into template-friendly context."""
    rule_results = readiness.get("rule_results", [])
    passing = [r for r in rule_results if r.get("result") == "passed"]
    blocking = [r for r in rule_results if r.get("result") != "passed" and r.get("result") != "skip"]

    # Generate next steps from blocking rules
    next_steps = []
    for r in blocking:
        rt = r.get("rule_type", "unknown")
        msg = r.get("message", "")
        next_steps.append(f"Fix: {rt} — {msg}")

    return {
        "current_env": readiness.get("source_environment", readiness.get("current_environment", "?")),
        "next_env": readiness.get("target_environment", readiness.get("next_environment", "?")),
        "status": readiness.get("status", "unknown"),
        "passed": readiness.get("passed_count", 0),
        "total": readiness.get("total_count", 0),
        "progress_pct": readiness.get("progress_pct", 0),
        "passing_rules": passing,
        "blocking_rules": blocking,
        "next_steps": next_steps,
    }


def render_template(
    template_name: str,
    package: CompiledContextPackage,
    project_root: str = ".",
    promotion_readiness: dict | None = None,
    scan_targets: list[dict] | None = None,
) -> str:
    """Render a single template by name."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template(template_name)
    ctx = _build_template_context(package, project_root, promotion_readiness, scan_targets)
    return template.render(**ctx)


def render_claude_md_section(
    package: CompiledContextPackage,
    project_root: str = ".",
    promotion_readiness: dict | None = None,
    scan_targets: list[dict] | None = None,
) -> str:
    """Render just the slim governance section for CLAUDE.md injection."""
    return render_template("CLAUDE.md.j2", package, project_root, promotion_readiness, scan_targets)


def inject_governance_into_claude_md(
    existing_content: str,
    governance_section: str,
) -> str:
    """Inject or replace the governance section in CLAUDE.md.

    If markers exist, replaces content between them.
    If no markers found, appends the section at the end.
    Preserves all developer content outside the markers.
    """
    if _MARKER_PATTERN.search(existing_content):
        return _MARKER_PATTERN.sub(governance_section.strip(), existing_content)

    # No markers — append at end
    separator = "\n\n" if existing_content.strip() else ""
    return existing_content.rstrip() + separator + governance_section


def render_all(
    package: CompiledContextPackage,
    project_root: Path,
    promotion_readiness: dict | None = None,
    scan_targets: list[dict] | None = None,
) -> dict[str, str]:
    """Render all templates and return {filename: content} mapping."""
    root_str = str(project_root)
    return {
        "GOVERNANCE.md": render_template("GOVERNANCE.md.j2", package, root_str, promotion_readiness, scan_targets),
        "claude_md_section": render_claude_md_section(package, root_str, promotion_readiness, scan_targets),
        ".mcp.json": render_template("mcp.json.j2", package, root_str),
        "pearl-dev.toml": render_template("pearl-dev.toml.j2", package, root_str),
        ".cursorrules": render_template("cursorrules.j2", package, root_str, promotion_readiness),
        "claude-settings.json": render_template("claude-settings.json.j2", package, root_str),
    }
