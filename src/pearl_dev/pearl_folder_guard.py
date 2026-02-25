""".pearl folder protection — shared detection logic.

Used by both Agent SDK hooks (pearl_dev.agent.hooks) and
Claude Code subprocess hooks (pearl_dev.hooks.pre_tool_call)
to block destructive operations on the .pearl/ governance folder.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# Destructive shell commands targeting .pearl
_DESTRUCTIVE_PATTERNS = [
    # Unix rm variants
    r"\brm\b\s+.*\.pearl",
    r"\brmdir\b\s+.*\.pearl",
    # Windows commands
    r"\bRemove-Item\b.*\.pearl",
    r"\bdel\b\s+.*\.pearl",
    r"\brd\b\s+.*\.pearl",
    # Python-based deletion
    r"\bshutil\.rmtree\b.*\.pearl",
    # Move-away (effectively deletion from expected location)
    r"\bmv\b\s+.*\.pearl",
    r"\bMove-Item\b.*\.pearl",
]

# Catch broad nuke commands that would include .pearl
_NUKE_PATTERNS = [
    r"\brm\b\s+-[rRf]+\s+\.\s*$",   # rm -rf .
    r"\brm\b\s+-[rRf]+\s+\*",        # rm -rf *
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DESTRUCTIVE_PATTERNS]
_NUKE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _NUKE_PATTERNS]

BLOCK_MESSAGE = (
    "BLOCKED: Deleting or moving .pearl/ is not allowed. "
    "This folder contains critical governance data (audit trail, cost ledger, "
    "approvals, policy). Use `pearl-dev sync` to restore from the PeaRL API "
    "if needed."
)


def is_pearl_destructive_bash(command: str) -> bool:
    """Return True if a bash command would destroy .pearl/ contents."""
    for pat in _COMPILED:
        if pat.search(command):
            return True
    for pat in _NUKE_COMPILED:
        if pat.search(command):
            return True
    return False


def is_pearl_write_target(file_path: str) -> bool:
    """Return True if a file path targets inside .pearl/.

    Used to block Write/Edit tool calls that would modify
    governance data directly. Agents should not tamper with
    audit trails, cost ledgers, or policy files.
    """
    normalized = file_path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    return ".pearl" in parts
