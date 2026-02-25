"""CLI entry point for pearl-agent workflows."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pearl_dev.agent.config import AgentConfig
from pearl_dev.agent.hooks import build_hooks
from pearl_dev.agent.runner import run_workflow
from pearl_dev.agent.workflows import SYSTEM_PROMPT


def _build_config(args: argparse.Namespace) -> AgentConfig:
    """Build AgentConfig from CLI args, falling back to pearl-dev.toml."""
    overrides: dict = {}

    if args.model:
        overrides["model"] = args.model
    if getattr(args, "verbose", False):
        overrides["verbose"] = True
    if getattr(args, "ci", False):
        overrides["permission_mode"] = "bypassPermissions"
    elif getattr(args, "dry_run", False):
        overrides["permission_mode"] = "plan"

    project_root = Path(args.directory).resolve() if getattr(args, "directory", None) else None

    if getattr(args, "project", None):
        overrides["project_id"] = args.project

    try:
        return AgentConfig.from_pearl_dev(project_root, **overrides)
    except (FileNotFoundError, Exception):
        # No pearl-dev.toml — use manual config
        pid = getattr(args, "project", None) or "unknown"
        root = project_root or Path.cwd().resolve()
        return AgentConfig(
            project_id=pid,
            environment=getattr(args, "env", "dev") or "dev",
            project_root=root,
            **{k: v for k, v in overrides.items() if k not in ("project_id",)},
        )


def _safe_print(text: str, **kwargs) -> None:
    """Print text, handling Windows encoding issues with emoji."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe, **kwargs)


def _on_text(text: str) -> None:
    """Print text output as it streams."""
    _safe_print(text, end="", flush=True)


def _on_tool(tool_name: str, tool_input: dict) -> None:
    """Print tool calls as they happen."""
    short_name = tool_name.removeprefix("mcp__pearl__")
    print(f"\n  -> {short_name}", flush=True)


def _print_footer(result, config: AgentConfig) -> None:
    """Print workflow result footer with cost transparency."""
    from pearl_dev.agent.cost_tracker import CostTracker

    print("\n---")
    print(f"Tools called: {len(result.tools_called)}")
    print(f"Success: {result.success}")
    if result.total_cost_usd is not None:
        print(f"Cost: ${result.total_cost_usd:.4f}")
    if result.duration_ms is not None:
        print(f"Duration: {result.duration_ms / 1000:.1f}s")

    # Show cumulative cost for this project
    try:
        tracker = CostTracker(config.project_root)
        summary = tracker.summary()
        if summary.total_runs > 1:
            print(f"Cumulative governance cost: ${summary.total_cost_usd:.4f} ({summary.total_runs} runs)")
    except Exception:
        pass


async def _run_scan(args: argparse.Namespace) -> int:
    """Run the scan workflow."""
    from pearl_dev.agent.workflows import scan_workflow

    config = _build_config(args)
    target = getattr(args, "target", "./src")
    prompt, tools = scan_workflow(config, target_path=target)
    hooks = build_hooks(config)

    print(f"PeaRL Agent: Scanning {config.project_id} ({config.environment})")
    print(f"Target: {target}")
    print("---")

    result = await run_workflow(
        config,
        workflow_prompt=prompt,
        workflow_name="scan",
        allowed_tools=tools,
        system_prompt=SYSTEM_PROMPT,
        hooks=hooks,
        on_text=_on_text if config.verbose else None,
        on_tool=_on_tool,
    )

    if not config.verbose and result.text_output:
        _safe_print(result.text_output)

    _print_footer(result, config)
    return 0 if result.success else 1


async def _run_promote(args: argparse.Namespace) -> int:
    """Run the promote workflow."""
    from pearl_dev.agent.workflows import promote_workflow

    config = _build_config(args)
    prompt, tools = promote_workflow(config)
    hooks = build_hooks(config)

    print(f"PeaRL Agent: Evaluating promotion for {config.project_id} ({config.environment})")
    print("---")

    result = await run_workflow(
        config,
        workflow_prompt=prompt,
        workflow_name="promote",
        allowed_tools=tools,
        system_prompt=SYSTEM_PROMPT,
        hooks=hooks,
        on_text=_on_text if config.verbose else None,
        on_tool=_on_tool,
    )

    if not config.verbose and result.text_output:
        _safe_print(result.text_output)

    _print_footer(result, config)
    return 0 if result.success else 1


async def _run_review(args: argparse.Namespace) -> int:
    """Run the review workflow."""
    from pearl_dev.agent.workflows import review_workflow

    config = _build_config(args)

    markdown_file = getattr(args, "markdown_file", None)
    if markdown_file:
        markdown_file = str(Path(markdown_file).resolve())

    prompt, tools = review_workflow(config, markdown_file=markdown_file)
    hooks = build_hooks(config)

    print(f"PeaRL Agent: Processing review for {config.project_id} ({config.environment})")
    print("---")

    result = await run_workflow(
        config,
        workflow_prompt=prompt,
        workflow_name="review",
        allowed_tools=tools,
        system_prompt=SYSTEM_PROMPT,
        hooks=hooks,
        on_text=_on_text if config.verbose else None,
        on_tool=_on_tool,
    )

    if not config.verbose and result.text_output:
        _safe_print(result.text_output)

    _print_footer(result, config)
    return 0 if result.success else 1


async def _run_onboard(args: argparse.Namespace) -> int:
    """Run the onboard workflow."""
    from pearl_dev.agent.workflows import onboard_workflow

    config = _build_config(args)
    ai = getattr(args, "ai", True)
    criticality = getattr(args, "criticality", "moderate")

    prompt, tools = onboard_workflow(config, ai_enabled=ai, criticality=criticality)
    hooks = build_hooks(config)

    print(f"PeaRL Agent: Onboarding {config.project_id}")
    print(f"AI enabled: {ai}, Criticality: {criticality}")
    print("---")

    result = await run_workflow(
        config,
        workflow_prompt=prompt,
        workflow_name="onboard",
        allowed_tools=tools,
        system_prompt=SYSTEM_PROMPT,
        hooks=hooks,
        on_text=_on_text if config.verbose else None,
        on_tool=_on_tool,
    )

    if not config.verbose and result.text_output:
        _safe_print(result.text_output)

    _print_footer(result, config)
    return 0 if result.success else 1


async def _run_custom(args: argparse.Namespace) -> int:
    """Run a custom workflow prompt."""
    from pearl_dev.agent.agents import all_agents
    from pearl_dev.agent.workflows import ALL_PEARL_TOOLS

    config = _build_config(args)
    hooks = build_hooks(config)
    agents = all_agents()

    print(f"PeaRL Agent: Custom workflow for {config.project_id} ({config.environment})")
    print("---")

    result = await run_workflow(
        config,
        workflow_prompt=args.prompt,
        workflow_name="custom",
        allowed_tools=ALL_PEARL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        agents=agents,
        hooks=hooks,
        on_text=_on_text if config.verbose else None,
        on_tool=_on_tool,
    )

    if not config.verbose and result.text_output:
        _safe_print(result.text_output)

    _print_footer(result, config)
    return 0 if result.success else 1


def _run_costs(args: argparse.Namespace) -> int:
    """Show governance cost report."""
    from pearl_dev.agent.cost_tracker import CostTracker

    config = _build_config(args)
    tracker = CostTracker(config.project_root)
    summary = tracker.summary()

    if getattr(args, "json", False):
        import json
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(summary.format_report())

    return 0


async def _dispatch(args: argparse.Namespace) -> int:
    """Route to the correct workflow handler."""
    # Costs is synchronous — handle separately
    if args.workflow == "costs":
        return _run_costs(args)

    handlers = {
        "scan": _run_scan,
        "promote": _run_promote,
        "review": _run_review,
        "onboard": _run_onboard,
        "run": _run_custom,
    }

    handler = handlers.get(args.workflow)
    if handler is None:
        print("Error: No workflow specified. Use --help for usage.", file=sys.stderr)
        return 1

    return await handler(args)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for pearl-agent."""
    parser = argparse.ArgumentParser(
        prog="pearl-agent",
        description="PeaRL Agent SDK orchestrator — automated governance workflows",
    )
    sub = parser.add_subparsers(dest="workflow")

    # pearl-agent scan
    p_scan = sub.add_parser("scan", help="Run AI security scan + compliance assessment")
    p_scan.add_argument("--target", default="./src", help="Target path to scan (default: ./src)")

    # pearl-agent promote
    p_promote = sub.add_parser("promote", help="Evaluate promotion readiness and promote if ready")

    # pearl-agent review
    p_review = sub.add_parser("review", help="Ingest security review and manage findings")
    p_review.add_argument("--markdown-file", help="Path to security review markdown file")

    # pearl-agent onboard
    p_onboard = sub.add_parser("onboard", help="Set up a new project with governance")
    p_onboard.add_argument("--ai", action="store_true", default=True, help="AI enabled (default: true)")
    p_onboard.add_argument("--no-ai", action="store_true", help="Not AI enabled")
    p_onboard.add_argument("--criticality", default="moderate",
                           choices=["low", "moderate", "high", "mission_critical"])

    # pearl-agent run
    p_run = sub.add_parser("run", help="Run a custom workflow prompt")
    p_run.add_argument("--prompt", required=True, help="Custom workflow prompt")

    # pearl-agent costs
    p_costs = sub.add_parser("costs", help="Show governance cost report")
    p_costs.add_argument("--json", action="store_true", help="Output as JSON")

    # Common options for all subcommands
    for p in [p_scan, p_promote, p_review, p_onboard, p_run, p_costs]:
        p.add_argument("--project", help="Project ID (default: from pearl-dev.toml)")
        p.add_argument("-d", "--directory", help="Project directory")
        p.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model")
        p.add_argument("--ci", action="store_true", help="CI mode (bypass permissions)")
        p.add_argument("--dry-run", action="store_true", help="Plan mode (show what would happen)")
        p.add_argument("--verbose", action="store_true", help="Stream text output in real-time")
        p.add_argument("--env", help="Environment override")

    args = parser.parse_args(argv)

    if not args.workflow:
        parser.print_help()
        sys.exit(1)

    exit_code = asyncio.run(_dispatch(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
