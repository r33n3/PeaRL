"""Parse /security-review markdown output into PeaRL findings.

Claude Code's ``/security-review`` command produces a markdown report.
This module extracts structured findings from that prose so they can be
ingested into PeaRL's finding pipeline and tracked as part of governance
requirements.

The parser is intentionally lenient — it extracts what it can from
several common report formats and gracefully ignores sections it
cannot parse.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Severity detection
# ---------------------------------------------------------------------------

_SEVERITY_KEYWORDS = {
    "critical": "critical",
    "high": "high",
    "medium": "moderate",
    "moderate": "moderate",
    "low": "low",
    "info": "low",
    "informational": "low",
    "minor": "low",
    "major": "high",
    "severe": "critical",
}

_SEVERITY_RE = re.compile(
    r"\b(" + "|".join(_SEVERITY_KEYWORDS.keys()) + r")\b",
    re.IGNORECASE,
)


def _detect_severity(text: str) -> str:
    """Detect severity from a block of text.

    Returns PeaRL severity string (critical/high/moderate/low).
    """
    match = _SEVERITY_RE.search(text)
    if match:
        return _SEVERITY_KEYWORDS.get(match.group(1).lower(), "moderate")
    return "moderate"


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[str, str] = {
    # Security categories
    "injection": "security",
    "xss": "security",
    "sql injection": "security",
    "authentication": "security",
    "authorization": "security",
    "csrf": "security",
    "ssrf": "security",
    "command injection": "security",
    "path traversal": "security",
    "buffer overflow": "security",
    "race condition": "security",
    "cryptograph": "security",
    "encryption": "security",
    "secret": "security",
    "credential": "security",
    "password": "security",
    "token": "security",
    "privilege": "security",
    "access control": "security",
    "validation": "security",
    "sanitiz": "security",
    "overflow": "security",
    "memory": "security",
    # Responsible AI
    "bias": "responsible_ai",
    "fairness": "responsible_ai",
    "toxic": "responsible_ai",
    "discriminat": "responsible_ai",
    "hallucin": "responsible_ai",
    "misinform": "responsible_ai",
    # Code quality (mapped to security for governance purposes)
    "error handling": "security",
    "exception": "security",
    "logging": "security",
    "dependency": "security",
}


def _detect_category(text: str) -> str:
    """Detect finding category from text."""
    text_lower = text.lower()
    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in text_lower:
            return category
    return "security"


# ---------------------------------------------------------------------------
# File path extraction
# ---------------------------------------------------------------------------

_FILE_PATH_RE = re.compile(
    r"(?:^|\s|`)"
    r"((?:[a-zA-Z]:[\\/])?(?:[\w./-]+/)?[\w.-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|yaml|yml|json|toml|md|txt|sh|sql|html|css|env|cfg|ini|conf))"
    r"(?:`|\s|$|:|\))",
    re.MULTILINE,
)

_LINE_REF_RE = re.compile(
    r"(?:line\s*#?\s*(\d+))|"
    r"(?::(\d+)(?:\s|$|,))|"
    r"(?:L(\d+))",
    re.IGNORECASE,
)


def _extract_file_paths(text: str) -> list[str]:
    """Extract file paths from text."""
    matches = _FILE_PATH_RE.findall(text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        normalized = m.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _extract_line_number(text: str) -> int | None:
    """Extract first line number reference from text."""
    match = _LINE_REF_RE.search(text)
    if match:
        for group in match.groups():
            if group:
                return int(group)
    return None


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+\*?\*?(.+?)\*?\*?\s*$", re.MULTILINE)
_BULLET_ITEM_RE = re.compile(r"^\s*[-*]\s+\*?\*?(.+?)\*?\*?\s*$", re.MULTILINE)


def parse_security_review(
    markdown: str,
    project_id: str,
    environment: str = "dev",
) -> dict[str, Any]:
    """Parse /security-review markdown output into PeaRL ingest format.

    The parser attempts several strategies:
    1. Look for numbered findings under severity headings
    2. Look for markdown headings that look like finding titles
    3. Fall back to extracting bullet-point issues

    Args:
        markdown: Raw markdown output from /security-review.
        project_id: PeaRL project ID for the findings.
        environment: Environment (dev, preprod, prod).

    Returns:
        Dict in PeaRL findings ingest batch format.
    """
    findings: list[dict[str, Any]] = []

    # Strategy 1: Split by headings and extract findings from each section
    sections = _split_by_headings(markdown)

    for section_title, section_body in sections:
        section_findings = _extract_findings_from_section(
            section_title, section_body, project_id, environment
        )
        findings.extend(section_findings)

    # Strategy 2: If no findings from sections, try numbered items
    if not findings:
        findings = _extract_numbered_findings(markdown, project_id, environment)

    # Strategy 3: If still nothing, treat each paragraph as a finding
    if not findings:
        findings = _extract_paragraph_findings(markdown, project_id, environment)

    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": f"secrev_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "source_system": "claude_security_review",
            "connector_version": "1.0.0",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "trust_label": "manual_unverified",
        },
        "findings": findings,
        "options": {
            "normalize_on_ingest": True,
            "strict_validation": False,
            "quarantine_on_error": True,
        },
    }


def _split_by_headings(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections."""
    sections: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(markdown))

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        sections.append((title, body))

    return sections


def _extract_findings_from_section(
    section_title: str,
    section_body: str,
    project_id: str,
    environment: str,
) -> list[dict[str, Any]]:
    """Extract findings from a single markdown section."""
    findings: list[dict[str, Any]] = []

    # Skip summary/overview sections
    skip_titles = {"summary", "overview", "introduction", "table of contents", "conclusion", "recommendations"}
    if section_title.lower().strip("# ") in skip_titles:
        return []

    # Check if section title looks like a severity label
    section_severity = _detect_severity(section_title)

    # Look for numbered or bulleted items in the section
    items = _NUMBERED_ITEM_RE.findall(section_body)
    if not items:
        # Try bullet items
        bullet_items = _BULLET_ITEM_RE.findall(section_body)
        if bullet_items:
            items = [(str(i + 1), item) for i, item in enumerate(bullet_items)]

    if items:
        for _num, item_text in items:
            # Get the full context for this item (text until next item)
            item_start = section_body.find(item_text)
            item_context = section_body[item_start:item_start + 500] if item_start >= 0 else item_text

            file_paths = _extract_file_paths(item_context)
            line_number = _extract_line_number(item_context)
            severity = _detect_severity(item_context) or section_severity
            category = _detect_category(item_context)

            findings.append(_build_finding(
                title=item_text[:200].strip(),
                description=item_context[:500].strip(),
                severity=severity,
                category=category,
                affected_files=file_paths,
                line_number=line_number,
                project_id=project_id,
                environment=environment,
            ))
    elif len(section_body) > 50:
        # Treat the whole section as one finding
        file_paths = _extract_file_paths(section_body)
        line_number = _extract_line_number(section_body)
        category = _detect_category(section_body)

        findings.append(_build_finding(
            title=section_title[:200],
            description=section_body[:500].strip(),
            severity=section_severity,
            category=category,
            affected_files=file_paths,
            line_number=line_number,
            project_id=project_id,
            environment=environment,
        ))

    return findings


def _extract_numbered_findings(
    markdown: str,
    project_id: str,
    environment: str,
) -> list[dict[str, Any]]:
    """Extract findings from numbered list items in the full document."""
    findings: list[dict[str, Any]] = []
    items = _NUMBERED_ITEM_RE.findall(markdown)

    for _num, item_text in items:
        if len(item_text.strip()) < 10:
            continue
        file_paths = _extract_file_paths(item_text)
        severity = _detect_severity(item_text)
        category = _detect_category(item_text)

        findings.append(_build_finding(
            title=item_text[:200].strip(),
            description=item_text.strip(),
            severity=severity,
            category=category,
            affected_files=file_paths,
            project_id=project_id,
            environment=environment,
        ))

    return findings


def _extract_paragraph_findings(
    markdown: str,
    project_id: str,
    environment: str,
) -> list[dict[str, Any]]:
    """Last resort: extract findings from paragraphs that mention issues."""
    findings: list[dict[str, Any]] = []
    issue_keywords = {"vulnerability", "issue", "risk", "concern", "finding", "problem", "flaw", "weakness", "bug"}

    paragraphs = re.split(r"\n\n+", markdown)
    for para in paragraphs:
        para = para.strip()
        if len(para) < 30:
            continue
        para_lower = para.lower()
        if any(kw in para_lower for kw in issue_keywords):
            file_paths = _extract_file_paths(para)
            severity = _detect_severity(para)
            category = _detect_category(para)

            # Use first sentence as title
            first_sentence = para.split(".")[0][:200]

            findings.append(_build_finding(
                title=first_sentence.strip(),
                description=para[:500].strip(),
                severity=severity,
                category=category,
                affected_files=file_paths,
                project_id=project_id,
                environment=environment,
            ))

    return findings


def _build_finding(
    title: str,
    description: str,
    severity: str,
    category: str,
    affected_files: list[str],
    project_id: str,
    environment: str,
    line_number: int | None = None,
) -> dict[str, Any]:
    """Build a single finding dict in PeaRL ingest format."""
    # Clean markdown formatting from title
    clean_title = re.sub(r"[*_`#]", "", title).strip()
    if not clean_title:
        clean_title = "Security Review Finding"

    return {
        "source": {
            "tool_name": "claude_security_review",
            "tool_type": "manual",
            "trust_label": "manual_unverified",
        },
        "project_id": project_id,
        "environment": environment,
        "category": category,
        "severity": severity,
        "confidence": "medium",
        "title": clean_title,
        "description": description,
        "affected_components": affected_files[:10],
        "cwe_ids": [],
        "compliance_refs": {},
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
        "metadata": {
            "source_type": "security_review",
            "line_number": line_number,
        },
    }
