"""Claude Code PreToolUse hook — checks policy before tool execution.

Reads tool invocation from stdin (JSON), evaluates policy, and:
- Exits 0 if allowed
- Exits non-zero (with reason on stderr) if blocked
- Checks for pre-existing approval if approval is required

Intended to be registered in .claude/settings.json:
  {"hooks": {"PreToolUse": [{"matcher": "*", "command": "python -m pearl_dev.hooks.pre_tool_call"}]}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Tool name -> PeaRL action mapping
TOOL_ACTION_MAP: dict[str, str] = {
    "Bash": "code_edit",
    "Write": "file_write",
    "Edit": "file_write",
    "Read": "file_read",
    "Glob": "file_read",
    "Grep": "file_read",
    "WebFetch": "web_search",
    "WebSearch": "web_search",
    "Task": "code_edit",
    "NotebookEdit": "file_write",
}


def main() -> None:
    from pearl_dev.audit import AuditLogger
    from pearl_dev.config import find_project_root, load_config
    from pearl_dev.context_loader import ContextLoader
    from pearl_dev.policy_engine import Decision, PolicyEngine

    # Read hook input from stdin
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)  # No input, allow

    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # Can't parse, allow (don't break the developer's flow)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    action = TOOL_ACTION_MAP.get(tool_name, tool_name.lower())

    # .pearl folder protection — runs before policy engine
    try:
        from pearl_dev.pearl_folder_guard import (
            BLOCK_MESSAGE,
            is_pearl_destructive_bash,
            is_pearl_write_target,
        )

        if tool_name == "Bash":
            command = tool_input.get("command", "")
            if is_pearl_destructive_bash(command):
                print(BLOCK_MESSAGE, file=sys.stderr)
                sys.exit(2)
        elif tool_name in ("Write", "Edit", "NotebookEdit"):
            file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
            if file_path and is_pearl_write_target(file_path):
                print(BLOCK_MESSAGE, file=sys.stderr)
                sys.exit(2)
    except Exception:
        pass  # Don't break developer flow if guard fails

    # Load policy
    try:
        root = find_project_root()
        config = load_config(root)
        package_path = root / config.package_path
        loader = ContextLoader(package_path)
        package = loader.load(verify_integrity=False)  # Skip hash check for speed in hook
        engine = PolicyEngine(package)
    except (FileNotFoundError, Exception):
        sys.exit(0)  # No package or config, allow (graceful degradation)

    # Check action
    result = engine.check_action(action)

    # Audit
    try:
        audit = AuditLogger(root / config.audit_path)
        audit.log(
            "pre_tool_call",
            action,
            result.decision,
            reason=result.reason,
            tool_name=tool_name,
            details={"hook": "PreToolUse"},
        )
    except Exception:
        pass  # Don't block on audit failure

    if result.decision == Decision.ALLOW:
        sys.exit(0)

    if result.decision == Decision.APPROVAL_REQUIRED:
        # Check for pre-existing approval
        try:
            from pearl_dev.approval_terminal import ApprovalManager
            approval_mgr = ApprovalManager(root / config.approvals_dir)
            pending = approval_mgr.list_pending()
            # Look for an approved request matching this action
            for req in pending:
                if req.get("action") == action:
                    checked = approval_mgr.check_approval(req["approval_id"])
                    if checked.get("status") == "approve":
                        sys.exit(0)
        except Exception:
            pass

        print(
            f"BLOCKED: Action '{action}' requires approval. "
            f"Run: pearl-dev approve <id> after requesting via pearl_request_approval MCP tool.",
            file=sys.stderr,
        )
        sys.exit(2)

    # BLOCKED
    print(f"BLOCKED: {result.reason}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
