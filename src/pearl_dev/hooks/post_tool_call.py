"""Claude Code PostToolUse hook — collects evidence after tool execution.

Always exits 0 (never blocks post-execution).

Intended to be registered in .claude/settings.json:
  {"hooks": {"PostToolUse": [{"matcher": "*", "command": "python -m pearl_dev.hooks.post_tool_call"}]}}
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    from pearl_dev.audit import AuditLogger
    from pearl_dev.config import find_project_root, load_config

    # Read hook input from stdin
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    # Truncate output for audit (avoid giant logs)
    tool_output = str(hook_input.get("tool_output", ""))[:500]

    try:
        root = find_project_root()
        config = load_config(root)
        audit = AuditLogger(root / config.audit_path)
        audit.log(
            "post_tool_call",
            tool_name,
            "completed",
            tool_name=tool_name,
            details={"hook": "PostToolUse", "output_preview": tool_output},
        )
    except Exception:
        pass  # Don't block on audit failure

    sys.exit(0)


if __name__ == "__main__":
    main()
