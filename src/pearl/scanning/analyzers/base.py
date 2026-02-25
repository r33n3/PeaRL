"""Base analyzer interface for PeaRL scanning.

Defines the base classes and data structures that all
scanner analyzers must implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pearl.scanning.types import AttackCategory, ComponentType, ScanSeverity


@dataclass
class AnalyzerFinding:
    """A finding from a scanner analyzer."""

    title: str
    description: str
    severity: ScanSeverity
    category: AttackCategory
    component_type: ComponentType
    component_name: str
    file_path: str | None = None
    line_number: int | None = None
    evidence: list[dict] = field(default_factory=list)
    remediation_summary: str | None = None
    remediation_steps: list[str] = field(default_factory=list)
    cwe_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AnalyzerResult:
    """Result from running an analyzer."""

    analyzer_name: str
    findings: list[AnalyzerFinding] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0


class BaseAnalyzer:
    """Base class for all analyzers."""

    name: str = "base"

    def analyze_directory(self, path: Path) -> AnalyzerResult:
        raise NotImplementedError

    def analyze_file(self, path: Path) -> AnalyzerResult:
        raise NotImplementedError

    def analyze_content(
        self, content: str, file_path: Path | None = None
    ) -> AnalyzerResult:
        raise NotImplementedError
