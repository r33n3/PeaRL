"""pearl-dev CLI — initialize, sync, serve, approve, reject, status, audit."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _detect_repo_url() -> str | None:
    """Auto-detect repo URL from git remote."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _detect_branch() -> str:
    """Auto-detect current git branch."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"


def _render_and_write_files(
    root: Path,
    package,
    promotion_readiness: dict | None = None,
    scan_targets: list[dict] | None = None,
) -> None:
    """Render all templates and write config files to disk."""
    from pearl_dev.template_renderer import inject_governance_into_claude_md, render_all

    rendered = render_all(package, root, promotion_readiness=promotion_readiness, scan_targets=scan_targets)

    # Write .pearl/GOVERNANCE.md (full governance reference)
    governance_path = root / ".pearl" / "GOVERNANCE.md"
    governance_path.parent.mkdir(parents=True, exist_ok=True)
    governance_path.write_text(rendered["GOVERNANCE.md"], encoding="utf-8")
    print(f"  Created: {governance_path}")

    # Inject slim governance section into CLAUDE.md (preserve developer content)
    claude_md_path = root / "CLAUDE.md"
    existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    updated = inject_governance_into_claude_md(existing, rendered["claude_md_section"])
    claude_md_path.write_text(updated, encoding="utf-8")
    print(f"  {'Updated' if existing else 'Created'}: {claude_md_path}")

    # Write .mcp.json
    (root / ".mcp.json").write_text(rendered[".mcp.json"], encoding="utf-8")
    print(f"  Created: {root / '.mcp.json'}")

    # Write pearl-dev.toml
    toml_path = root / ".pearl" / "pearl-dev.toml"
    toml_path.write_text(rendered["pearl-dev.toml"], encoding="utf-8")
    print(f"  Created: {toml_path}")

    # Write .cursorrules
    (root / ".cursorrules").write_text(rendered[".cursorrules"], encoding="utf-8")
    print(f"  Created: {root / '.cursorrules'}")

    # Create approvals dir
    approvals_dir = root / ".pearl" / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {approvals_dir}")

    # Write .claude/settings.json with hooks (skip if exists)
    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(rendered["claude-settings.json"], encoding="utf-8")
        print(f"  Created: {settings_path}")
    else:
        print(f"  Skipped: {settings_path} (already exists)")


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize pearl-dev in the current project.

    Two modes:
    - Bootstrap mode (--project): registers project, scan target, compiles context via API
    - Offline mode: uses pre-existing compiled-context-package.json
    """
    from pearl_dev.context_loader import ContextLoader

    if args.project:
        # Bootstrap mode: use specified or current directory (no .pearl/ yet)
        root = (Path(args.directory) if args.directory else Path.cwd()).resolve()
    else:
        # Offline mode: need existing .pearl/ directory
        from pearl_dev.config import find_project_root
        root = find_project_root(Path(args.directory) if args.directory else None)
    pearl_dir = root / ".pearl"
    pearl_dir.mkdir(parents=True, exist_ok=True)
    package_path = pearl_dir / "compiled-context-package.json"

    scan_targets = None
    readiness = None

    if args.project:
        # --- Bootstrap mode: register + fetch from API ---
        from pearl_dev.api_client import PearlAPIClient

        api_url = args.api_url or "http://localhost:8080/api/v1"
        client = PearlAPIClient(api_url)
        project_id = args.project
        # Auto-prefix proj_ if not already present
        if not project_id.startswith("proj_"):
            project_id = f"proj_{project_id}"
        env = args.env or "dev"

        print(f"Bootstrapping PeaRL for {project_id} ({env})...")

        ai_enabled = not args.no_ai
        criticality = args.criticality or "moderate"

        # 1. Register project
        result = client.register_project(
            project_id, environment=env, ai_enabled=ai_enabled,
            business_criticality=criticality,
        )
        if result:
            print(f"  Registered project: {project_id}")
        else:
            print(f"  Project already exists: {project_id} (continuing setup)")

        # 2. Upsert org baseline (sensible defaults)
        baseline_result = client.upsert_org_baseline(project_id, {
            "schema_version": "1.0",
            "kind": "PearlOrgBaseline",
            "baseline_id": f"orgb_{project_id.removeprefix('proj_')}",
            "org_name": project_id.removeprefix("proj_"),
            "defaults": {
                "coding": {
                    "secure_coding_standard_required": True,
                    "secret_hardcoding_forbidden": True,
                    "dependency_pinning_required": True,
                },
                "logging": {
                    "structured_logging_required": True,
                    "pii_in_logs_forbidden_by_default": True,
                },
                "iam": {"least_privilege_required": True},
                "network": {"deny_by_default_preferred": True},
                "responsible_ai": {
                    "ai_use_disclosure_required_for_user_facing": ai_enabled,
                    "model_provenance_logging_required": ai_enabled,
                    "human_oversight_required_for_high_impact_actions": ai_enabled,
                },
                "testing": {
                    "unit_tests_required": True,
                    "security_tests_baseline_required": True,
                    "rai_evals_required_for_ai_enabled_apps": ai_enabled,
                },
            },
        })
        if baseline_result:
            print("  Applied org baseline")

        # 3. Upsert application spec
        app_id = project_id.removeprefix("proj_").lower().replace(" ", "-")
        spec_result = client.upsert_app_spec(project_id, {
            "schema_version": "1.0",
            "kind": "PearlApplicationSpec",
            "application": {
                "app_id": app_id,
                "owner_team": "default",
                "business_criticality": criticality,
                "external_exposure": "internal_only",
                "ai_enabled": ai_enabled,
            },
            "architecture": {
                "components": [{"id": "app", "type": "service"}],
            },
        })
        if spec_result:
            print("  Applied application spec")

        # 4. Upsert environment profile
        env_result = client.upsert_env_profile(project_id, {
            "schema_version": "1.0",
            "profile_id": f"envp_{app_id}_{env}",
            "environment": env,
            "delivery_stage": "bootstrap",
            "risk_level": "low",
            "autonomy_mode": "supervised_autonomous",
        })
        if env_result:
            print(f"  Applied environment profile: {env}")

        # 5. Auto-detect repo URL and register scan target
        if not args.no_scan_target:
            repo_url = _detect_repo_url()
            if repo_url:
                branch = _detect_branch()
                st_result = client.register_scan_target(project_id, repo_url, branch=branch)
                if st_result:
                    print(f"  Registered scan target: {repo_url} ({branch})")
                else:
                    print(f"  Scan target already registered: {repo_url}")
            else:
                print("  No git remote detected (skipping scan target)")

        # 6. Trigger context compilation
        compile_result = client.compile_context(project_id)
        if compile_result:
            print("  Compiled context package")
        else:
            print("  Warning: Could not compile context")

        # 7. Fetch compiled context package
        pkg_data = client.get_compiled_package(project_id)
        if pkg_data:
            package_path.write_text(json.dumps(pkg_data, indent=2), encoding="utf-8")
            print(f"  Fetched: {package_path}")
        else:
            if not package_path.exists():
                print("Error: Could not fetch compiled package from API", file=sys.stderr)
                sys.exit(1)
            print("  Warning: Using local compiled package")

        # 8. Fetch promotion readiness
        readiness = client.get_promotion_readiness(project_id)
        if readiness:
            readiness_path = pearl_dir / "promotion-readiness.json"
            readiness_path.write_text(json.dumps(readiness, indent=2), encoding="utf-8")
            print(f"  Fetched: {readiness_path}")

        # 9. Fetch scan targets
        scan_targets = client.get_scan_targets(project_id)
        if scan_targets:
            st_path = pearl_dir / "scan-targets.json"
            st_path.write_text(json.dumps(scan_targets, indent=2), encoding="utf-8")
            print(f"  Fetched: {st_path}")

    else:
        # --- Offline mode: use existing package ---
        if not package_path.exists():
            print(f"Error: No compiled context package at {package_path}", file=sys.stderr)
            print("  Hint: Use --project to bootstrap from the PeaRL API", file=sys.stderr)
            sys.exit(1)

    # Load and render
    loader = ContextLoader(package_path)
    package = loader.load(verify_integrity=not args.project)

    _render_and_write_files(root, package, promotion_readiness=readiness, scan_targets=scan_targets)

    print()
    print(f"pearl-dev initialized for project: {package.project_identity.project_id}")
    print(f"Environment: {package.project_identity.environment}")
    print(f"Autonomy mode: {package.autonomy_policy.mode}")
    print()
    print("Claude Code: Hooks registered in .claude/settings.json")
    print("Claude Code: MCP server registered in .mcp.json")
    pid = package.project_identity.project_id
    env_name = package.project_identity.environment
    print(f"MCP server: pearl [{pid}] ({env_name})")
    print("Governance: .pearl/GOVERNANCE.md (full details)")
    print("Governance: CLAUDE.md (slim governance section injected)")
    print()
    print("Claude Desktop: Add this to your claude_desktop_config.json")
    python_path = sys.executable.replace("\\", "/")
    root_str = str(root).replace("\\", "/")
    desktop_cfg = {
        "pearl": {
            "command": python_path,
            "args": ["-m", "pearl_dev.unified_mcp", "--directory", root_str],
        }
    }
    print(f'  Location: %APPDATA%/Claude/claude_desktop_config.json')
    print()
    print(f'  "mcpServers": {json.dumps(desktop_cfg, indent=4)}')


def _load_sync_state(root: Path) -> dict:
    """Load .pearl/sync-state.json or return empty defaults."""
    state_path = root / ".pearl" / "sync-state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_sync_state(root: Path, state: dict) -> None:
    """Persist sync state to .pearl/sync-state.json."""
    state_path = root / ".pearl" / "sync-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _push_telemetry(root: Path, config, client) -> None:
    """Push audit events and cost data to the PeaRL API."""
    from pearl_dev.audit import AuditLogger

    state = _load_sync_state(root)

    # Push audit events
    audit_path = root / config.audit_path
    if audit_path.exists():
        audit = AuditLogger(audit_path)
        since = None
        if state.get("last_audit_sync"):
            from datetime import datetime
            try:
                since = datetime.fromisoformat(state["last_audit_sync"])
            except (ValueError, TypeError):
                since = None

        entries = audit.query(since=since)
        if entries:
            result = client.push_audit_events(config.project_id, entries)
            if result:
                print(f"  Pushed: {result['created']} audit events")
                state["last_audit_sync"] = entries[-1].get("timestamp", "")
            else:
                print("  Warning: Could not push audit events (API unavailable)")

    # Push cost entries
    cost_path = root / ".pearl" / "cost-ledger.jsonl"
    if cost_path.exists():
        from pearl_dev.agent.cost_tracker import CostTracker
        tracker = CostTracker(root)
        all_entries = tracker.load_all()

        if state.get("last_cost_sync"):
            all_entries = [e for e in all_entries if e.timestamp > state["last_cost_sync"]]

        if all_entries:
            cost_dicts = [e.to_dict() for e in all_entries]
            result = client.push_governance_costs(config.project_id, cost_dicts)
            if result:
                print(f"  Pushed: {result['created']} cost entries")
                state["last_cost_sync"] = all_entries[-1].timestamp
            else:
                print("  Warning: Could not push cost entries (API unavailable)")

    _save_sync_state(root, state)


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync latest state from PeaRL API and re-render templates."""
    from pearl_dev.api_client import PearlAPIClient
    from pearl_dev.config import find_project_root, load_config
    from pearl_dev.context_loader import ContextLoader
    from pearl_dev.template_renderer import inject_governance_into_claude_md, render_all

    root = find_project_root(Path(args.directory) if args.directory else None)
    config = load_config(root)

    api_url = args.api_url or config.api_url
    client = PearlAPIClient(api_url)

    print(f"Syncing with {api_url}...")

    # ── Push local data to API ────────────────────────────────────────
    _push_telemetry(root, config, client)

    # ── Pull from API ─────────────────────────────────────────────────

    # 1. Fetch compiled context package
    pkg_data = client.get_compiled_package(config.project_id)
    if pkg_data:
        pkg_path = root / ".pearl" / "compiled-context-package.json"
        pkg_path.write_text(json.dumps(pkg_data, indent=2), encoding="utf-8")
        print(f"  Updated: {pkg_path}")
    else:
        print("  Warning: Could not fetch compiled package (using local)")

    # 2. Fetch promotion readiness
    readiness = client.get_promotion_readiness(config.project_id)
    readiness_path = root / ".pearl" / "promotion-readiness.json"
    if readiness:
        readiness_path.write_text(json.dumps(readiness, indent=2), encoding="utf-8")
        print(f"  Updated: {readiness_path}")
    else:
        # Remove stale readiness if API has no evaluation
        if readiness_path.exists():
            readiness_path.unlink()
        print("  No promotion evaluation available")

    # 3. Fetch scan targets
    scan_targets = client.get_scan_targets(config.project_id)
    scan_targets_path = root / ".pearl" / "scan-targets.json"
    if scan_targets is not None:
        scan_targets_path.write_text(json.dumps(scan_targets, indent=2), encoding="utf-8")
        print(f"  Updated: {scan_targets_path}")
    else:
        scan_targets = []
        print("  No scan targets available")

    # 4. Re-render templates
    package_path = root / ".pearl" / "compiled-context-package.json"
    loader = ContextLoader(package_path)
    package = loader.load(verify_integrity=False)

    rendered = render_all(package, root, promotion_readiness=readiness, scan_targets=scan_targets)

    # Write .pearl/GOVERNANCE.md (full governance reference)
    governance_path = root / ".pearl" / "GOVERNANCE.md"
    governance_path.write_text(rendered["GOVERNANCE.md"], encoding="utf-8")
    print(f"  Updated: {governance_path}")

    # Inject slim governance section into CLAUDE.md (preserve developer content)
    claude_md_path = root / "CLAUDE.md"
    existing = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    updated = inject_governance_into_claude_md(existing, rendered["claude_md_section"])
    claude_md_path.write_text(updated, encoding="utf-8")
    print(f"  Updated: {claude_md_path}")

    (root / ".cursorrules").write_text(rendered[".cursorrules"], encoding="utf-8")
    print(f"  Updated: {root / '.cursorrules'}")

    # Print summary
    print()
    if readiness:
        src = readiness.get("source_environment", "?")
        tgt = readiness.get("target_environment", "?")
        passed = readiness.get("passed_count", 0)
        total = readiness.get("total_count", 0)
        pct = readiness.get("progress_pct", 0)
        print(f"Synced: {src} -> {tgt} readiness: {passed}/{total} ({pct}%)")
    else:
        print(f"Synced: {config.project_id} (no promotion evaluation)")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the unified MCP stdio server."""
    from pearl_dev.config import find_project_root, load_config
    from pearl_dev.unified_mcp import PearlUnifiedMCPServer

    root = find_project_root(Path(args.directory) if args.directory else None)
    config = load_config(root)

    server = PearlUnifiedMCPServer(
        project_root=root,
        project_id=config.project_id,
        environment=config.environment,
        api_url=config.api_url,
    )
    server.run_stdio()


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a pending approval request."""
    from pearl_dev.approval_terminal import ApprovalManager
    from pearl_dev.config import find_project_root, load_config

    root = find_project_root()
    config = load_config(root)
    mgr = ApprovalManager(root / config.approvals_dir)

    try:
        decision = mgr.decide(args.approval_id, "approve", decided_by="developer")
        print(f"Approved: {decision['approval_id']}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_reject(args: argparse.Namespace) -> None:
    """Reject a pending approval request."""
    from pearl_dev.approval_terminal import ApprovalManager
    from pearl_dev.config import find_project_root, load_config

    root = find_project_root()
    config = load_config(root)
    mgr = ApprovalManager(root / config.approvals_dir)

    try:
        decision = mgr.decide(
            args.approval_id, "reject",
            decided_by="developer",
            notes=args.reason or "",
        )
        print(f"Rejected: {decision['approval_id']}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args: argparse.Namespace) -> None:
    """Show policy summary, pending approvals, recent audit."""
    from pearl_dev.approval_terminal import ApprovalManager
    from pearl_dev.audit import AuditLogger
    from pearl_dev.config import find_project_root, load_config
    from pearl_dev.context_loader import ContextLoader
    from pearl_dev.policy_engine import PolicyEngine

    root = find_project_root()
    config = load_config(root)

    # Policy summary
    loader = ContextLoader(root / config.package_path)
    package = loader.load(verify_integrity=False)
    engine = PolicyEngine(package)
    summary = engine.get_policy_summary()

    print("=" * 60)
    print(f"  Project:     {summary['project_id']}")
    print(f"  Environment: {summary['environment']}")
    print(f"  Autonomy:    {summary['autonomy_mode']}")
    print(f"  Allowed:     {len(summary['allowed_actions'])} actions")
    print(f"  Blocked:     {len(summary['blocked_actions'])} actions")
    print("=" * 60)

    # Pending approvals
    mgr = ApprovalManager(root / config.approvals_dir)
    pending = mgr.list_pending()
    if pending:
        print(f"\nPending Approvals ({len(pending)}):")
        for p in pending:
            print(f"  [{p['approval_id']}] {p['action']} — {p['reason']}")
    else:
        print("\nNo pending approvals.")

    # Recent audit entries
    audit = AuditLogger(root / config.audit_path)
    entries = audit.query()
    recent = entries[-5:] if entries else []
    if recent:
        print(f"\nRecent Audit ({len(recent)} of {len(entries)} total):")
        for e in recent:
            print(f"  [{e['timestamp'][:19]}] {e['event_type']}: {e['action']} -> {e['decision']}")
    else:
        print("\nNo audit entries.")


def cmd_audit(args: argparse.Namespace) -> None:
    """Query audit log."""
    from pearl_dev.audit import AuditLogger
    from pearl_dev.config import find_project_root, load_config

    root = find_project_root()
    config = load_config(root)
    audit = AuditLogger(root / config.audit_path)

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since)

    entries = audit.query(since=since, event_type=args.type)

    if not entries:
        print("No matching audit entries.")
        return

    for e in entries:
        print(json.dumps(e))


def cmd_integrations(args: argparse.Namespace) -> None:
    """Manage external integration endpoints."""
    from pearl_dev.api_client import PearlAPIClient
    from pearl_dev.config import find_project_root, load_config

    root = find_project_root(Path(args.directory) if args.directory else None)
    config = load_config(root)

    api_url = args.api_url or config.api_url
    client = PearlAPIClient(api_url)

    action = args.action

    if action == "list":
        results = client.list_integrations(config.project_id)
        if results is None:
            print("Error: Could not reach PeaRL API", file=sys.stderr)
            sys.exit(1)
        if not results:
            print("No integrations configured.")
            return
        print(f"Integrations for {config.project_id}:")
        for ep in results:
            status = "enabled" if ep.get("enabled") else "disabled"
            last_sync = ep.get("last_sync_at", "never")
            print(f"  [{ep['endpoint_id']}] {ep['name']} ({ep['adapter_type']}/{ep['integration_type']}) — {status} — last sync: {last_sync}")

    elif action == "add":
        if not args.name or not args.type:
            print("Error: --name and --type are required", file=sys.stderr)
            sys.exit(1)
        body = {
            "name": args.name,
            "adapter_type": args.type,
            "integration_type": args.direction or "source",
            "category": args.category or args.type,
            "base_url": args.url or "",
        }
        if args.auth_env:
            body["auth_config"] = {"auth_type": "bearer", "bearer_token_env": args.auth_env}
        result = client.register_integration(config.project_id, body)
        if result:
            print(f"Registered: {result['name']} ({result['endpoint_id']})")
        else:
            print("Error: Could not register integration", file=sys.stderr)
            sys.exit(1)

    elif action == "test":
        if not args.endpoint_id:
            print("Error: endpoint_id is required", file=sys.stderr)
            sys.exit(1)
        result = client.test_integration(config.project_id, args.endpoint_id)
        if result:
            print(f"Test result for {result.get('endpoint_name', args.endpoint_id)}: {result.get('status', 'unknown')}")
            if result.get("error"):
                print(f"  Error: {result['error']}")
        else:
            print("Error: Could not test integration", file=sys.stderr)
            sys.exit(1)

    elif action == "pull":
        if not args.endpoint_id:
            print("Error: endpoint_id is required", file=sys.stderr)
            sys.exit(1)
        result = client.pull_integration(config.project_id, args.endpoint_id)
        if result:
            print(f"Pulled {result.get('findings_pulled', 0)} findings from {result.get('endpoint_name', args.endpoint_id)}")
        else:
            print("Error: Could not pull from integration", file=sys.stderr)
            sys.exit(1)

    elif action == "remove":
        if not args.endpoint_id:
            print("Error: endpoint_id is required", file=sys.stderr)
            sys.exit(1)
        result = client.disable_integration(config.project_id, args.endpoint_id)
        if result:
            print(f"Disabled: {args.endpoint_id}")
        else:
            print("Error: Could not disable integration", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)


def cmd_agent(args: argparse.Namespace) -> None:
    """Delegate to the pearl-agent CLI."""
    from pearl_dev.agent.cli import main as agent_main

    agent_main(args.workflow_args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pearl-dev",
        description="Developer-side policy enforcement for autonomous coding agents",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Initialize pearl-dev in the current project")
    p_init.add_argument("-d", "--directory", help="Project directory (default: auto-discover)")
    p_init.add_argument("--project", help="Project ID for API bootstrap (e.g. proj_myapp)")
    p_init.add_argument("--env", help="Environment (default: dev)", default=None)
    p_init.add_argument("--api-url", help="PeaRL API URL (default: http://localhost:8080/api/v1)")
    p_init.add_argument("--no-scan-target", action="store_true", help="Skip scan target registration")
    p_init.add_argument("--no-ai", action="store_true", help="Project does not use AI (default: AI enabled)")
    p_init.add_argument("--criticality", choices=["low", "moderate", "high", "mission_critical"],
                        help="Business criticality (default: moderate)")

    # sync
    p_sync = sub.add_parser("sync", help="Sync latest state from PeaRL API and re-render templates")
    p_sync.add_argument("-d", "--directory", help="Project directory (default: auto-discover)")
    p_sync.add_argument("--api-url", help="PeaRL API URL (overrides pearl-dev.toml)")

    # serve
    p_serve = sub.add_parser("serve", help="Start MCP stdio server")
    p_serve.add_argument("-d", "--directory", help="Project directory (default: auto-discover)")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a pending request")
    p_approve.add_argument("approval_id", help="The approval ID to approve")

    # reject
    p_reject = sub.add_parser("reject", help="Reject a pending request")
    p_reject.add_argument("approval_id", help="The approval ID to reject")
    p_reject.add_argument("--reason", help="Reason for rejection")

    # status
    sub.add_parser("status", help="Show policy summary and pending approvals")

    # audit
    p_audit = sub.add_parser("audit", help="Query audit log")
    p_audit.add_argument("--since", help="ISO timestamp to filter from")
    p_audit.add_argument("--type", help="Event type to filter")

    # integrations
    p_intg = sub.add_parser("integrations", help="Manage external integration endpoints")
    p_intg.add_argument("action", choices=["list", "add", "test", "pull", "remove"],
                        help="Integration action")
    p_intg.add_argument("endpoint_id", nargs="?", help="Endpoint ID (for test/pull/remove)")
    p_intg.add_argument("-d", "--directory", help="Project directory (default: auto-discover)")
    p_intg.add_argument("--api-url", help="PeaRL API URL (overrides pearl-dev.toml)")
    p_intg.add_argument("--name", help="Integration name (for add)")
    p_intg.add_argument("--type", help="Adapter type: snyk, semgrep, trivy, slack, jira, github_issues (for add)")
    p_intg.add_argument("--direction", choices=["source", "sink", "bidirectional"],
                        help="Integration direction (for add, default: source)")
    p_intg.add_argument("--category", help="Integration category (for add)")
    p_intg.add_argument("--url", help="Base URL for the external service (for add)")
    p_intg.add_argument("--auth-env", help="Env var name holding bearer token (for add)")

    # agent (delegates to pearl_dev.agent.cli)
    p_agent = sub.add_parser("agent", help="Run Agent SDK workflows (e.g. scan, promote)")
    p_agent.add_argument("workflow_args", nargs=argparse.REMAINDER,
                         help="Arguments passed to pearl-agent CLI")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "sync": cmd_sync,
        "serve": cmd_serve,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "status": cmd_status,
        "audit": cmd_audit,
        "integrations": cmd_integrations,
        "agent": cmd_agent,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
