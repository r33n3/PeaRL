"""
Governance Context Drift Detector

Scans recent git commits (configurable lookback, default 50 commits)
for changes to governance-critical source files without a corresponding
update to CLAUDE.md in the same commit range.

Run as a pre-commit hook or CI step.

Usage:
  python scripts/pearl_context_drift_check.py [--lookback 50]

Exit codes:
  0 = no drift detected
  1 = drift detected (CLAUDE.md may be stale relative to code changes)
  2 = git not available or repo not found
"""

import argparse
import subprocess
import sys
from pathlib import Path


# Files whose changes should always be reflected in CLAUDE.md
GOVERNANCE_CRITICAL_FILES = [
    "src/pearl/config.py",
    "src/pearl/dependencies.py",
    "src/pearl/api/middleware/auth.py",
    "src/pearl/errors/handlers.py",
    "src/pearl/mcp/tools.py",
    "scripts/pearl_bash_guard.py",
]

CLAUDE_MD = "CLAUDE.md"


def _git(*args: str) -> tuple[int, str]:
    """Run a git command, return (returncode, stdout)."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def _get_changed_files(lookback: int) -> set[str] | None:
    """Return the set of files changed across the last N commits, or None on error."""
    rc, out = _git("log", "--name-only", "--pretty=format:", f"-{lookback}")
    if rc != 0:
        return None
    # Each line is a filename; blank lines separate commits
    files: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if line:
            files.add(line)
    return files


def _repo_root() -> Path | None:
    """Return the repo root path, or None if not in a git repo."""
    rc, out = _git("rev-parse", "--show-toplevel")
    if rc != 0:
        return None
    return Path(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for governance context drift between CLAUDE.md and critical source files."
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=50,
        metavar="N",
        help="Number of recent commits to inspect (default: 50)",
    )
    args = parser.parse_args()

    # Verify we are in a git repo
    root = _repo_root()
    if root is None:
        print("ERROR: Not in a git repository (or git is not available).", file=sys.stderr)
        return 2

    changed_files = _get_changed_files(args.lookback)
    if changed_files is None:
        print("ERROR: Unable to read git log.", file=sys.stderr)
        return 2

    if not changed_files:
        print(f"No commits found in last {args.lookback} lookback. Nothing to check.")
        return 0

    # Determine which governance-critical files changed
    changed_critical = [f for f in GOVERNANCE_CRITICAL_FILES if f in changed_files]

    if not changed_critical:
        print(f"OK: No governance-critical files changed in last {args.lookback} commits.")
        return 0

    # Check whether CLAUDE.md was also updated in the same range
    claude_updated = CLAUDE_MD in changed_files

    if claude_updated:
        print(
            f"OK: {len(changed_critical)} governance-critical file(s) changed and "
            f"CLAUDE.md was also updated in the last {args.lookback} commits."
        )
        for f in sorted(changed_critical):
            print(f"  changed: {f}")
        return 0

    # Drift detected
    print(
        f"DRIFT DETECTED: {len(changed_critical)} governance-critical file(s) changed "
        f"in last {args.lookback} commits without a corresponding CLAUDE.md update.\n"
    )
    print("Changed governance-critical files:")
    for f in sorted(changed_critical):
        print(f"  {f}")
    print(
        f"\nCLAUDE.md was NOT updated in the same range.\n"
        f"Review CLAUDE.md for accuracy and update if the governance constraints have changed.\n"
        f"Reference: docs/security_research/governance_hardening_plan_v2.md §3.1"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
