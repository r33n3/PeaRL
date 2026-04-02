"""SPEC.md coverage checker — maps security criteria to test coverage.

Reads SPEC.md from the repo root, parses [x] (implemented) and [ ] (open)
criteria, then checks whether a corresponding test file exists by searching
tests/ for keywords from each criterion.

Findings are emitted as pytest warnings (not failures) — this is a coverage
audit tool, not a blocking gate. Run it when evaluating sprint completeness.

Usage:
    PEARL_LOCAL=1 pytest tests/security/spec_validation.py -v -s

Output:
    Each [ ] criterion produces a pytest.warns entry.
    Summary: N criteria covered, M uncovered (with keyword search).
"""

import re
import warnings
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
SPEC_PATH = _REPO_ROOT / "SPEC.md"
TESTS_PATH = _REPO_ROOT / "tests"


# ---------------------------------------------------------------------------
# SPEC.md parser
# ---------------------------------------------------------------------------

def _parse_spec_criteria(spec_text: str) -> list[dict]:
    """Extract all criteria lines from SPEC.md.

    Returns a list of dicts:
      {
        "text": str,          # criterion description
        "covered": bool,      # True = [x], False = [ ]
        "section": str,       # nearest heading above the criterion
      }
    """
    criteria = []
    current_section = "Unknown"

    for line in spec_text.splitlines():
        # Track section headings
        heading_match = re.match(r"^#{1,3}\s+(.+)", line)
        if heading_match:
            current_section = heading_match.group(1).strip()
            continue

        # Match checkbox criteria: - [x] ... or - [ ] ...
        criterion_match = re.match(r"^\s*[-*]\s+\[([ x])\]\s+(.+)", line)
        if criterion_match:
            marker = criterion_match.group(1)
            text = criterion_match.group(2).strip()
            criteria.append({
                "text": text,
                "covered": marker == "x",
                "section": current_section,
            })

    return criteria


# ---------------------------------------------------------------------------
# Test file keyword search
# ---------------------------------------------------------------------------

def _extract_keywords(criterion_text: str) -> list[str]:
    """Extract searchable keywords from a criterion description.

    Strips common stop-words and returns meaningful tokens ≥ 4 chars.
    """
    stop_words = {
        "with", "from", "that", "this", "when", "have", "been", "must",
        "only", "also", "each", "into", "than", "then", "they", "will",
        "should", "added", "all", "any", "are", "via", "for", "the",
        "and", "not", "per", "on", "in", "to", "of", "or", "at", "by",
        "can", "if", "no", "be", "is", "it", "as", "an", "a",
    }
    # Tokenise: split on non-alphanumeric, lowercase
    tokens = re.split(r"[^a-zA-Z0-9_]+", criterion_text.lower())
    return [t for t in tokens if len(t) >= 4 and t not in stop_words]


def _search_tests_for_keywords(keywords: list[str]) -> list[Path]:
    """Return test files that contain at least one of the keywords."""
    if not keywords or not TESTS_PATH.exists():
        return []

    matches = []
    for test_file in TESTS_PATH.rglob("test_*.py"):
        content = test_file.read_text(encoding="utf-8", errors="ignore").lower()
        if any(kw in content for kw in keywords):
            matches.append(test_file)

    return matches


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------

def _load_criteria() -> list[dict]:
    if not SPEC_PATH.exists():
        pytest.skip(f"SPEC.md not found at {SPEC_PATH}")
    return _parse_spec_criteria(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("criterion", _load_criteria(), ids=lambda c: c["text"][:60])
def test_spec_criterion_coverage(criterion, recwarn):
    """Each SPEC.md criterion is checked for test coverage.

    [x] criteria:  verified that a matching test file exists (or noted as missing).
    [ ] criteria:  reported as a warning (open item, not a blocking failure).

    This test never fails — it only warns. Run with -v -s to see the full report.
    """
    text = criterion["text"]
    covered_in_spec = criterion["covered"]
    section = criterion["section"]
    keywords = _extract_keywords(text)
    matching_tests = _search_tests_for_keywords(keywords)

    if covered_in_spec:
        if not matching_tests:
            warnings.warn(
                f"[SPEC {section}] Marked [x] but no test found for: '{text}' "
                f"(keywords: {keywords})",
                stacklevel=2,
            )
        # [x] with test coverage — pass silently
    else:
        # [ ] open item — warn regardless of whether a test exists
        if matching_tests:
            rel_paths = [str(p.relative_to(_REPO_ROOT)) for p in matching_tests[:3]]
            warnings.warn(
                f"[SPEC {section}] OPEN — possible test coverage in {rel_paths}: '{text}'",
                stacklevel=2,
            )
        else:
            warnings.warn(
                f"[SPEC {section}] OPEN — no test coverage found for: '{text}' "
                f"(keywords searched: {keywords})",
                stacklevel=2,
            )


def test_spec_coverage_summary():
    """Print a coverage summary: N implemented, M open, P with test matches."""
    criteria = _load_criteria()

    implemented = [c for c in criteria if c["covered"]]
    open_items = [c for c in criteria if not c["covered"]]

    # Check open items for potential test coverage
    open_with_tests = []
    open_without_tests = []
    for c in open_items:
        kws = _extract_keywords(c["text"])
        if _search_tests_for_keywords(kws):
            open_with_tests.append(c)
        else:
            open_without_tests.append(c)

    summary = (
        f"\nSPEC.md coverage summary:\n"
        f"  Implemented [x]:           {len(implemented)}\n"
        f"  Open [ ] with test match:  {len(open_with_tests)}\n"
        f"  Open [ ] no test found:    {len(open_without_tests)}\n"
        f"  Total criteria:            {len(criteria)}\n"
    )
    print(summary)  # visible with pytest -s

    if open_without_tests:
        warnings.warn(
            f"{len(open_without_tests)} SPEC criteria have no test coverage: "
            + ", ".join(f"'{c['text'][:40]}'" for c in open_without_tests[:5])
            + ("..." if len(open_without_tests) > 5 else ""),
            stacklevel=2,
        )

    # This test always passes — it is a reporting tool only
    assert len(criteria) > 0, "SPEC.md parsed no criteria — check the file format"
