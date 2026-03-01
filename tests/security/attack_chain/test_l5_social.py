"""L5 — Social Engineering: No Bypass Documentation in Source

Attack chain level 5: an autonomous agent with file-read access scans
the codebase for documentation that explains how to obtain reviewer
privileges (e.g., 'set PEARL_LOCAL_REVIEWER=1 to act as reviewer').
Such documentation reduces the cost of social engineering prompts targeted
at human operators.

Hard control tested (static analysis):
  - Source files outside docs/security_research/ must not contain phrases
    that explain how to obtain reviewer privileges
  - Verified post-Phase-3 strip: src/pearl/dependencies.py comment removed

This is a static analysis test — no running server required.

Reference: pearl_autonomous_attack_research.md L5
Control: docs stripped per governance_hardening_plan_v2.md §3.2
"""

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[3]  # PeaRL/

# Phrases that describe how to obtain reviewer privileges.
# These are the social engineering vectors.
DANGEROUS_PHRASES = [
    "to act as a security reviewer",
    "grants reviewer",
    "reviewer role requires",
    "to approve as reviewer",
    r"PEARL_LOCAL_REVIEWER\s*=\s*1.*reviewer",  # assignment + context
    r"set.*PEARL_LOCAL_REVIEWER.*reviewer",
    "additionally require PEARL_LOCAL_REVIEWER",
    "PEARL_LOCAL_REVIEWER=1",
]

# Only scan source and script files. The threat model is an agent using the
# Read tool to explore the codebase and find bypass instructions in Python
# source files. User-facing documentation (README.md, docs/, .env.example)
# and test files are out of scope for this check.
SCAN_DIRS = ["src", "scripts"]

# Directories explicitly excluded within the scan dirs
EXCLUDED_DIR_PREFIXES = [
    "docs/security_research/",
    "PeaRL_spec/",
]

# File extensions to scan
SCAN_EXTENSIONS = {".py"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_scan(path: Path) -> bool:
    """Return True if this file should be checked for dangerous phrases."""
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return False

    rel_str = str(rel).replace("\\", "/")

    # Only scan files within the approved source directories
    if not any(rel_str.startswith(d + "/") for d in SCAN_DIRS):
        return False

    # Skip excluded directories
    for prefix in EXCLUDED_DIR_PREFIXES:
        if rel_str.startswith(prefix):
            return False

    # Skip hidden dirs (.git, .venv, __pycache__, node_modules, etc.)
    parts = rel.parts
    for part in parts[:-1]:
        if part.startswith(".") or part in ("__pycache__", "node_modules"):
            return False

    return path.suffix in SCAN_EXTENSIONS


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, line_text, matched_phrase) for dangerous phrases."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits

    for lineno, line in enumerate(text.splitlines(), start=1):
        for phrase in DANGEROUS_PHRASES:
            if re.search(phrase, line, re.IGNORECASE):
                hits.append((lineno, line.strip(), phrase))
                break  # one match per line is enough
    return hits


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_l5_no_bypass_documentation_in_source():
    """
    L5 control: source files outside docs/security_research/ must not contain
    documentation that explains how to obtain reviewer privileges.

    Attack vector: an agent reading codebase files finds a comment like
    'set PEARL_LOCAL_REVIEWER=1 to act as reviewer' and uses this to construct
    a social engineering prompt asking the human operator to enable the flag.

    Verified change: src/pearl/dependencies.py lines 37-39 stripped in Phase 3.
    """
    offenders = []

    scan_roots = [REPO_ROOT / d for d in SCAN_DIRS if (REPO_ROOT / d).is_dir()]
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if not _should_scan(path):
                continue
            hits = _scan_file(path)
            if hits:
                rel = path.relative_to(REPO_ROOT)
                for lineno, line, phrase in hits:
                    offenders.append(f"  {rel}:{lineno}: matched {phrase!r}\n    → {line}")

    assert not offenders, (
        "Social engineering documentation found in source files:\n"
        + "\n".join(offenders)
        + "\n\nRemove or replace explanatory comments that describe how to obtain "
        "reviewer privileges. Reference: governance_hardening_plan_v2.md §3.2"
    )


def test_l5_dependencies_py_comment_stripped():
    """
    Specific regression: the three-line bypass comment in dependencies.py must
    be absent (stripped in Phase 3 Task 3.2).
    """
    deps_file = REPO_ROOT / "src" / "pearl" / "dependencies.py"
    assert deps_file.exists(), f"Expected {deps_file} to exist"
    content = deps_file.read_text(encoding="utf-8")
    assert "additionally require PEARL_LOCAL_REVIEWER=1" not in content, (
        "The bypass mechanism explanation was found in src/pearl/dependencies.py. "
        "This comment should have been stripped in Phase 3. "
        "Reference: governance_hardening_plan_v2.md §3.2"
    )
