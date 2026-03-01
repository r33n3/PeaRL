#!/usr/bin/env python3
"""
PeaRL PreToolUse Bash Guard Hook

Reads a Claude Code tool-use event from stdin (JSON), checks the proposed
Bash command against a blocklist of PeaRL-governance-specific dangerous patterns,
and exits:
  - 0  → allow (no output)
  - 2  → block (prints reason to stdout for Claude to see)

SCOPE INTENT: This guard blocks only PeaRL governance bypass patterns — direct
calls to the governance decide endpoints and writes of governance bypass flags
to config files. It does NOT block general system administration commands
(ps, kill, docker, systemctl, etc.) which are needed for legitimate prototyping
and autonomous development workflows.

Install in ~/.claude/settings.json:
  {
    "hooks": {
      "PreToolUse": [{
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python /path/to/scripts/pearl_bash_guard.py"}]
      }]
    }
  }
"""

import json
import re
import sys

# Each entry: (human-readable label, compiled regex)
#
# These patterns target PeaRL governance bypass specifically.
# General system commands (ps, kill, docker, systemctl) are intentionally
# NOT blocked — they are needed for legitimate prototyping work.
BLOCKED_PATTERNS = [
    # Direct governance API calls: bypasses the MCP profile role gate
    (
        "direct PeaRL governance API call via curl (/approvals/*/decide or /exceptions/*/decide)",
        re.compile(r"\bcurl\b.*/(approvals|exceptions)/[^/\s]+/decide"),
    ),
    # Shell writes of governance bypass flags into .env or any env file
    (
        "writing PEARL_LOCAL_REVIEWER flag to a config file",
        re.compile(r"PEARL_LOCAL_REVIEWER\s*=.*(?:>>|>|tee)"),
    ),
    (
        "writing PEARL_LOCAL_REVIEWER flag via redirect to .env",
        re.compile(r"(?:>>|>|tee\s+(-a\s+)?)\s*\.env.*PEARL_LOCAL_REVIEWER|PEARL_LOCAL_REVIEWER.*(?:>>|>|\btee\b)"),
    ),
    # Any shell redirect that writes the reviewer bypass flag
    (
        "appending governance bypass flag to .env",
        re.compile(r"PEARL_LOCAL_REVIEWER"),
    ),
]


def check_command(command: str) -> tuple[bool, str]:
    """Return (blocked, reason). blocked=True means the command should be denied."""
    for label, pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            return True, label
    return False, ""


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        # Can't parse — allow and let Claude Code handle it
        sys.exit(0)

    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    blocked, reason = check_command(command)
    if blocked:
        print(
            f"[PeaRL Bash Guard] BLOCKED — {reason}. "
            "This command is prohibited by the PeaRL governance security policy. "
            "If a governance action requires elevated privileges, use pearl_request_approval "
            "or pearl_create_exception and inform the user."
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
