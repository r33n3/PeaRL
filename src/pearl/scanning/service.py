"""ScanningService — orchestrates AI security scanning within PeaRL.

Central service that coordinates all analyzers, converts findings to
PeaRL ingest format, runs compliance assessments, generates diagrams,
and recommends guardrails.

Usage::

    service = ScanningService()
    result = await service.scan_and_ingest(
        target_path=Path("./src"),
        project_id="proj_abc123",
        session=db_session,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pearl.scanning.analyzers.base import AnalyzerFinding, AnalyzerResult
from pearl.scanning.compliance.assessor import (
    AssessmentResult,
    ComplianceAssessor,
)
from pearl.scanning.findings_bridge import (
    convert_analyzer_finding,
    convert_multiple_results,
)
from pearl.scanning.policy.guardrails import (
    Guardrail,
    get_default_guardrails,
)
from pearl.scanning.types import AttackCategory, ComponentType, ScanSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analyzer registry — maps name → lazy-import callable
# ---------------------------------------------------------------------------

AVAILABLE_ANALYZERS: dict[str, str] = {
    "context": "pearl.scanning.analyzers.context.ContextAnalyzer",
    "mcp": "pearl.scanning.analyzers.mcp.MCPAnalyzer",
    "workflow": "pearl.scanning.analyzers.workflow.WorkflowAnalyzer",
    "attack_surface": "pearl.scanning.analyzers.attack_surface.AttackSurfaceAnalyzer",
    "rag": "pearl.scanning.analyzers.rag.RAGAnalyzer",
    "model_file": "pearl.scanning.analyzers.model_file.ModelFileScanner",
}

# Analyzers that require outputs from other analyzers
_META_ANALYZERS = {"attack_surface"}

# File extensions each analyzer cares about
_ANALYZER_FILE_HINTS = {
    "context": {".md", ".txt", ".cursorrules"},
    "mcp": {".json"},
    "workflow": {".py", ".yaml", ".yml"},
    "rag": {".py"},
    "model_file": {
        ".pt", ".pth", ".bin", ".gguf", ".safetensors",
        ".onnx", ".pkl", ".pickle", ".h5", ".keras",
    },
}


def _import_analyzer(dotted_path: str) -> type:
    """Import an analyzer class from its dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


# ---------------------------------------------------------------------------
# Scan result data structures
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """Result from a complete scanning run."""

    scan_id: str
    project_id: str
    environment: str
    target_path: str
    started_at: str
    completed_at: str | None = None
    analyzers_run: list[str] = field(default_factory=list)
    analyzer_results: list[AnalyzerResult] = field(default_factory=list)
    total_findings: int = 0
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings_by_analyzer: dict[str, int] = field(default_factory=dict)
    compliance_assessment: AssessmentResult | None = None
    guardrail_recommendations: list[Guardrail] = field(default_factory=list)
    ingested_batch_id: str | None = None
    errors: list[str] = field(default_factory=list)
    diagrams: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-safe dict."""
        severity_counts = dict(self.findings_by_severity)
        analyzer_counts = dict(self.findings_by_analyzer)

        result: dict[str, Any] = {
            "scan_id": self.scan_id,
            "project_id": self.project_id,
            "environment": self.environment,
            "target_path": self.target_path,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "analyzers_run": self.analyzers_run,
            "total_findings": self.total_findings,
            "findings_by_severity": severity_counts,
            "findings_by_analyzer": analyzer_counts,
            "errors": self.errors,
        }

        if self.compliance_assessment:
            result["compliance_assessment"] = {
                "overall_score": self.compliance_assessment.overall_compliance_score,
                "frameworks": {
                    fw.value: {
                        "score": fa.compliance_score,
                        "total_requirements": fa.total_requirements,
                        "compliant": fa.compliant_count,
                        "non_compliant": fa.non_compliant_count,
                    }
                    for fw, fa in self.compliance_assessment.frameworks.items()
                },
            }

        if self.guardrail_recommendations:
            result["guardrail_recommendations"] = [
                {
                    "id": g.id,
                    "name": g.name,
                    "category": g.guardrail_type.value,
                    "severity": g.severity.value,
                }
                for g in self.guardrail_recommendations
            ]

        if self.diagrams:
            result["diagrams"] = {k: "(xml content)" for k in self.diagrams}

        return result


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class ScanningService:
    """Orchestrates AI security scanning within PeaRL."""

    def __init__(self) -> None:
        self._assessor = ComplianceAssessor()
        self._guardrail_registry = get_default_guardrails()

    # ----- public API -----

    def scan_target(
        self,
        target_path: Path | str,
        project_id: str,
        analyzers: list[str] | None = None,
        environment: str = "dev",
    ) -> ScanResult:
        """Run selected analyzers against a code/config target.

        This is a synchronous scan (no DB interaction). Use
        :meth:`scan_and_ingest` for the full pipeline with DB persistence.

        Args:
            target_path: Directory or file to scan.
            project_id: PeaRL project ID.
            analyzers: List of analyzer names to run (default: all).
            environment: Environment label.

        Returns:
            ScanResult with findings and compliance data.
        """
        from pearl.services.id_generator import generate_id

        target_path = Path(target_path)
        scan_id = generate_id("scan_")
        started_at = datetime.now(timezone.utc).isoformat()

        requested = analyzers or list(AVAILABLE_ANALYZERS.keys())
        # Separate meta analyzers (attack_surface depends on others)
        primary = [a for a in requested if a not in _META_ANALYZERS]
        meta = [a for a in requested if a in _META_ANALYZERS]

        all_results: list[AnalyzerResult] = []
        analyzers_run: list[str] = []
        errors: list[str] = []

        # --- Phase 1: Run primary analyzers ---
        for name in primary:
            if name not in AVAILABLE_ANALYZERS:
                errors.append(f"Unknown analyzer: {name}")
                continue
            try:
                result = self._run_analyzer(name, target_path)
                all_results.append(result)
                analyzers_run.append(name)
            except Exception as exc:
                logger.exception("Analyzer %s failed", name)
                errors.append(f"{name}: {exc}")

        # --- Phase 2: Run meta analyzers that consume phase-1 outputs ---
        for name in meta:
            if name not in AVAILABLE_ANALYZERS:
                errors.append(f"Unknown analyzer: {name}")
                continue
            try:
                result = self._run_meta_analyzer(name, all_results, target_path)
                all_results.append(result)
                analyzers_run.append(name)
            except Exception as exc:
                logger.exception("Meta analyzer %s failed", name)
                errors.append(f"{name}: {exc}")

        # --- Aggregate findings ---
        all_findings: list[AnalyzerFinding] = []
        findings_by_severity: dict[str, int] = {}
        findings_by_analyzer: dict[str, int] = {}

        for ar in all_results:
            findings_by_analyzer[ar.analyzer_name] = len(ar.findings)
            for f in ar.findings:
                all_findings.append(f)
                sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1

        # --- Compliance assessment ---
        compliance = self._assess_compliance(all_findings, scan_id)

        # --- Guardrail recommendations ---
        guardrails = self._recommend_guardrails(all_findings)

        # --- Generate diagrams ---
        diagrams = self._generate_diagrams(
            all_results, all_findings, project_id, environment
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        return ScanResult(
            scan_id=scan_id,
            project_id=project_id,
            environment=environment,
            target_path=str(target_path),
            started_at=started_at,
            completed_at=completed_at,
            analyzers_run=analyzers_run,
            analyzer_results=all_results,
            total_findings=len(all_findings),
            findings_by_severity=findings_by_severity,
            findings_by_analyzer=findings_by_analyzer,
            compliance_assessment=compliance,
            guardrail_recommendations=guardrails,
            errors=errors,
            diagrams=diagrams,
        )

    async def scan_and_ingest(
        self,
        target_path: Path | str,
        project_id: str,
        session: Any,
        analyzers: list[str] | None = None,
        environment: str = "dev",
    ) -> ScanResult:
        """Scan + convert to PeaRL findings + ingest into DB.

        Full pipeline:
        1. Run analyzers (synchronous static analysis)
        2. Convert findings to PeaRL ingest format via findings_bridge
        3. Persist findings through FindingRepository
        4. Create batch record
        5. Return ScanResult

        Args:
            target_path: Directory or file to scan.
            project_id: PeaRL project ID.
            session: SQLAlchemy AsyncSession for DB persistence.
            analyzers: List of analyzer names (default: all).
            environment: Environment label.

        Returns:
            ScanResult with ingested_batch_id populated.
        """
        from pearl.repositories.finding_repo import (
            FindingBatchRepository,
            FindingRepository,
        )
        from pearl.services.id_generator import generate_id

        # Step 1: Run the scan
        result = self.scan_target(
            target_path=target_path,
            project_id=project_id,
            analyzers=analyzers,
            environment=environment,
        )

        # Step 2: Convert to PeaRL ingest format
        if not result.analyzer_results:
            return result

        ingest_batch = convert_multiple_results(
            results=result.analyzer_results,
            project_id=project_id,
            environment=environment,
        )

        batch_id = ingest_batch["source_batch"]["batch_id"]

        # Step 3: Persist findings
        finding_repo = FindingRepository(session)
        accepted = 0
        quarantined = 0

        for finding_data in ingest_batch["findings"]:
            try:
                await finding_repo.create(
                    finding_id=finding_data["finding_id"],
                    project_id=finding_data["project_id"],
                    environment=finding_data["environment"],
                    category=finding_data["category"],
                    severity=finding_data["severity"],
                    title=finding_data["title"],
                    source=finding_data["source"],
                    full_data=finding_data,
                    normalized=False,
                    detected_at=datetime.fromisoformat(finding_data["detected_at"]),
                    batch_id=batch_id,
                    cwe_ids=finding_data.get("cwe_ids"),
                    compliance_refs=finding_data.get("compliance_refs"),
                    status=finding_data.get("status", "open"),
                )
                accepted += 1
            except Exception as exc:
                logger.warning("Failed to persist finding: %s", exc)
                quarantined += 1

        # Step 3b: Persist completion markers for analyzers with 0 findings.
        # The gate evaluator derives completed_analyzers from findings, so
        # analyzers that find nothing would appear as "not completed" without this.
        analyzers_with_findings = set()
        for finding_data in ingest_batch["findings"]:
            tool_name = finding_data.get("source", {}).get("tool_name", "")
            if tool_name.startswith("pearl_scan_"):
                analyzers_with_findings.add(tool_name.replace("pearl_scan_", ""))

        for analyzer_name in result.analyzers_run:
            if analyzer_name not in analyzers_with_findings:
                marker_id = generate_id("find_")
                now_iso = datetime.now(timezone.utc).isoformat()
                try:
                    await finding_repo.create(
                        finding_id=marker_id,
                        project_id=project_id,
                        environment=environment,
                        category="security",
                        severity="info",
                        title=f"Scan completed: {analyzer_name} (0 issues found)",
                        source={
                            "tool_name": f"pearl_scan_{analyzer_name}",
                            "tool_type": "mass",
                            "trust_label": "trusted_internal",
                        },
                        full_data={
                            "finding_id": marker_id,
                            "title": f"Scan completed: {analyzer_name} (0 issues found)",
                            "category": "security",
                            "severity": "info",
                            "status": "closed",
                            "source": {
                                "tool_name": f"pearl_scan_{analyzer_name}",
                                "tool_type": "mass",
                                "trust_label": "trusted_internal",
                            },
                            "detected_at": now_iso,
                        },
                        normalized=False,
                        detected_at=datetime.now(timezone.utc),
                        batch_id=batch_id,
                        status="closed",
                    )
                    accepted += 1
                except Exception as exc:
                    logger.warning("Failed to persist analyzer marker: %s", exc)

        # Step 4: Create batch record
        batch_repo = FindingBatchRepository(session)
        await batch_repo.create(
            batch_id=batch_id,
            source_system=ingest_batch["source_batch"]["source_system"],
            trust_label=ingest_batch["source_batch"]["trust_label"],
            accepted_count=accepted,
            quarantined_count=quarantined,
            normalized_count=0,
        )

        await session.flush()

        result.ingested_batch_id = batch_id
        return result

    def assess_compliance(
        self,
        findings: list[AnalyzerFinding],
        frameworks: list[str] | None = None,
        scan_id: str = "",
    ) -> AssessmentResult:
        """Run compliance scoring against findings.

        Args:
            findings: List of AnalyzerFinding objects.
            frameworks: Optional list of framework names to assess.
            scan_id: Optional scan ID for tracking.

        Returns:
            AssessmentResult with per-framework scores.
        """
        return self._assess_compliance(findings, scan_id, frameworks)

    def recommend_guardrails(
        self,
        findings: list[AnalyzerFinding],
    ) -> list[Guardrail]:
        """Recommend guardrails based on findings.

        Args:
            findings: List of AnalyzerFinding objects.

        Returns:
            List of recommended Guardrail objects.
        """
        return self._recommend_guardrails(findings)

    def generate_diagrams(
        self,
        analyzer_results: list[AnalyzerResult],
        findings: list[AnalyzerFinding],
        project_id: str,
        environment: str = "dev",
    ) -> dict[str, str]:
        """Generate draw.io diagrams from scan results.

        Returns:
            Dict mapping diagram name to draw.io XML string.
        """
        return self._generate_diagrams(
            analyzer_results, findings, project_id, environment
        )

    # ----- private: individual analyzer runners -----

    def _run_analyzer(self, name: str, target_path: Path) -> AnalyzerResult:
        """Run a single primary analyzer and return its AnalyzerResult."""
        dotted = AVAILABLE_ANALYZERS[name]
        cls = _import_analyzer(dotted)
        analyzer = cls()

        if name == "context":
            return self._run_context(analyzer, target_path)
        elif name == "mcp":
            return self._run_mcp(analyzer, target_path)
        elif name == "workflow":
            return self._run_workflow(analyzer, target_path)
        elif name == "rag":
            return self._run_rag(analyzer, target_path)
        elif name == "model_file":
            return self._run_model_file(analyzer, target_path)
        else:
            raise ValueError(f"No runner for analyzer: {name}")

    def _run_context(self, analyzer: Any, target_path: Path) -> AnalyzerResult:
        """Run context analyzer on directory."""
        if target_path.is_file():
            results = [analyzer.analyze_file(target_path)]
        else:
            results = analyzer.analyze_directory(target_path, recursive=True)
        return analyzer.to_analyzer_result(results)

    def _run_mcp(self, analyzer: Any, target_path: Path) -> AnalyzerResult:
        """Run MCP analyzer — searches for MCP config files."""
        all_results = []
        if target_path.is_file():
            all_results.extend(analyzer.analyze_config_file(target_path))
        else:
            # Search for MCP config files
            mcp_patterns = [
                "**/.mcp.json",
                "**/mcp_config.json",
                "**/mcp.json",
                "**/.cursor/mcp.json",
                "**/.vscode/mcp.json",
            ]
            for pattern in mcp_patterns:
                for config_file in target_path.glob(pattern):
                    try:
                        results = analyzer.analyze_config_file(config_file)
                        all_results.extend(results)
                    except Exception as exc:
                        logger.warning("MCP analysis failed for %s: %s", config_file, exc)
        return analyzer.to_analyzer_result(all_results)

    def _run_workflow(self, analyzer: Any, target_path: Path) -> AnalyzerResult:
        """Run workflow analyzer — searches for Python/YAML files with framework imports."""
        all_results = []
        if target_path.is_file():
            result = analyzer.analyze_file(target_path)
            all_results.append(result)
        else:
            # Scan Python and YAML files for workflow patterns
            for ext in ("**/*.py", "**/*.yaml", "**/*.yml"):
                for fpath in target_path.glob(ext):
                    try:
                        result = analyzer.analyze_file(fpath)
                        if result.findings:
                            all_results.append(result)
                    except Exception:
                        pass
        # Merge into single AnalyzerResult
        merged_findings: list[AnalyzerFinding] = []
        for wr in all_results:
            ar = analyzer.to_analyzer_result(wr)
            merged_findings.extend(ar.findings)
        return AnalyzerResult(
            analyzer_name="workflow",
            findings=merged_findings,
        )

    def _run_rag(self, analyzer: Any, target_path: Path) -> AnalyzerResult:
        """Run RAG analyzer on directory."""
        if target_path.is_file():
            result = analyzer.analyze_file(target_path)
        else:
            result = analyzer.analyze_directory(target_path)
        return analyzer.to_analyzer_result(result)

    def _run_model_file(self, analyzer: Any, target_path: Path) -> AnalyzerResult:
        """Run model file scanner on directory."""
        if target_path.is_file():
            results = [analyzer.scan_file(target_path)]
        else:
            results = analyzer.scan_directory(target_path)
        return analyzer.to_analyzer_result(results)

    # ----- private: meta analyzers -----

    def _run_meta_analyzer(
        self,
        name: str,
        prior_results: list[AnalyzerResult],
        target_path: Path,
    ) -> AnalyzerResult:
        """Run a meta analyzer that depends on other results."""
        if name == "attack_surface":
            return self._run_attack_surface(prior_results, target_path)
        raise ValueError(f"No meta-runner for: {name}")

    def _run_attack_surface(
        self,
        prior_results: list[AnalyzerResult],
        target_path: Path,
    ) -> AnalyzerResult:
        """Run attack surface analyzer using prior results as input."""
        from pearl.scanning.analyzers.attack_surface import AttackSurfaceAnalyzer

        analyzer = AttackSurfaceAnalyzer()

        # Build component map from prior findings
        components: dict[str, ComponentType] = {}
        interactions: list[tuple[str, str, str]] = []

        for ar in prior_results:
            for finding in ar.findings:
                comp_name = finding.component_name or finding.file_path or "unknown"
                comp_type = finding.component_type
                if isinstance(comp_type, str):
                    try:
                        comp_type = ComponentType(comp_type)
                    except ValueError:
                        comp_type = ComponentType.CODE
                components[comp_name] = comp_type

        # Add some default components if we found AI-related things
        if any(ar.analyzer_name == "context" for ar in prior_results):
            components.setdefault("system_prompt", ComponentType.CONTEXT)
        if any(ar.analyzer_name == "mcp" for ar in prior_results):
            components.setdefault("mcp_server", ComponentType.MCP_SERVER)
        if any(ar.analyzer_name == "workflow" for ar in prior_results):
            components.setdefault("agent_workflow", ComponentType.WORKFLOW)
        if any(ar.analyzer_name == "rag" for ar in prior_results):
            components.setdefault("knowledge_base", ComponentType.KNOWLEDGE)
        if any(ar.analyzer_name == "model_file" for ar in prior_results):
            components.setdefault("model", ComponentType.MODEL)

        # If no components were discovered, return empty result
        if not components:
            return AnalyzerResult(analyzer_name="attack_surface")

        # Build basic interactions between discovered components
        comp_names = list(components.keys())
        if "system_prompt" in components and "agent_workflow" in components:
            interactions.append(("system_prompt", "agent_workflow", "context_injection"))
        if "mcp_server" in components and "agent_workflow" in components:
            interactions.append(("agent_workflow", "mcp_server", "tool_invocation"))
        if "knowledge_base" in components and "agent_workflow" in components:
            interactions.append(("knowledge_base", "agent_workflow", "rag_retrieval"))

        result = analyzer.analyze(components, interactions)
        return analyzer.to_analyzer_result(result)

    # ----- private: compliance -----

    def _assess_compliance(
        self,
        findings: list[AnalyzerFinding],
        scan_id: str,
        frameworks: list[str] | None = None,
    ) -> AssessmentResult:
        """Run compliance assessment on findings."""
        # Convert AnalyzerFinding to the dict format the assessor expects
        finding_dicts = []
        for f in findings:
            cat = f.category
            if isinstance(cat, str):
                try:
                    cat = AttackCategory(cat)
                except ValueError:
                    pass
            sev = f.severity
            if isinstance(sev, str):
                try:
                    sev = ScanSeverity(sev)
                except ValueError:
                    pass
            finding_dicts.append({
                "category": cat,
                "severity": sev,
                "id": f.title,
            })
        return self._assessor.assess(finding_dicts, scan_id=scan_id)

    # ----- private: guardrails -----

    def _recommend_guardrails(
        self,
        findings: list[AnalyzerFinding],
    ) -> list[Guardrail]:
        """Recommend guardrails based on finding categories."""
        # Map finding categories to guardrail categories
        category_needs: set[str] = set()

        for f in findings:
            cat = f.category
            cat_str = cat.value if hasattr(cat, "value") else str(cat)

            if cat_str in ("prompt_injection", "jailbreak", "system_prompt_leakage"):
                category_needs.add("input_validation")
                category_needs.add("content_moderation")
            elif cat_str in ("sensitive_info", "data_leakage", "secrets_exposure"):
                category_needs.add("data_protection")
                category_needs.add("output_filtering")
            elif cat_str in ("excessive_agency", "privilege_escalation"):
                category_needs.add("access_control")
            elif cat_str in ("unbounded_consumption", "denial_of_service"):
                category_needs.add("rate_limiting")
                category_needs.add("resource_limits")
            elif cat_str in ("supply_chain", "insecure_plugin", "data_model_poisoning"):
                category_needs.add("model_protection")
            elif cat_str in ("bias", "toxicity", "misinformation", "hallucination"):
                category_needs.add("content_moderation")
                category_needs.add("output_filtering")
            else:
                category_needs.add("audit_logging")

        # Always recommend audit logging if there are findings
        if findings:
            category_needs.add("audit_logging")

        # Filter guardrails by guardrail_type
        recommended = []
        for guardrail in self._guardrail_registry.get_all():
            gt = guardrail.guardrail_type
            gt_str = gt.value if hasattr(gt, "value") else str(gt)
            if gt_str in category_needs:
                recommended.append(guardrail)

        return recommended

    # ----- private: diagrams -----

    def _generate_diagrams(
        self,
        analyzer_results: list[AnalyzerResult],
        findings: list[AnalyzerFinding],
        project_id: str,
        environment: str,
    ) -> dict[str, str]:
        """Generate threat model and topology diagrams from scan results."""
        from pearl.scanning.diagrams.threat_model import generate_threat_model_diagram
        from pearl.scanning.diagrams.topology import generate_topology_diagram

        diagrams: dict[str, str] = {}

        # Build component map for diagrams
        components: dict[str, str] = {}
        interactions_list: list[dict[str, Any]] = []
        attack_vectors: list[dict[str, Any]] = []
        vuln_paths: list[dict[str, Any]] = []
        findings_by_component: dict[str, str] = {}

        for ar in analyzer_results:
            for f in ar.findings:
                comp_name = f.component_name or f.file_path or ar.analyzer_name
                comp_type = f.component_type
                comp_type_str = comp_type.value if hasattr(comp_type, "value") else str(comp_type)
                components[comp_name] = comp_type_str

                sev = f.severity
                sev_str = sev.value if hasattr(sev, "value") else str(sev)

                # Track highest severity per component
                sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
                current = findings_by_component.get(comp_name, "info")
                if sev_order.get(sev_str, 0) > sev_order.get(current, 0):
                    findings_by_component[comp_name] = sev_str

                # Build attack vectors from findings
                cat = f.category
                cat_str = cat.value if hasattr(cat, "value") else str(cat)
                attack_vectors.append({
                    "name": f.title[:80],
                    "severity": sev_str,
                    "target": comp_name,
                    "category": cat_str,
                })

        # Check for attack surface results
        for ar in analyzer_results:
            if ar.analyzer_name == "attack_surface" and ar.metadata:
                if "vulnerability_paths" in ar.metadata:
                    vuln_paths.extend(ar.metadata["vulnerability_paths"])
                if "interactions" in ar.metadata:
                    interactions_list.extend(ar.metadata["interactions"])

        if components:
            try:
                diagrams["threat_model"] = generate_threat_model_diagram(
                    components=components,
                    attack_vectors=attack_vectors[:50],
                    vulnerability_paths=vuln_paths[:20],
                    interactions=interactions_list,
                    title=f"Threat Model — {project_id} ({environment})",
                )
            except Exception as exc:
                logger.warning("Failed to generate threat model diagram: %s", exc)

            try:
                diagrams["topology"] = generate_topology_diagram(
                    components=components,
                    interactions=interactions_list,
                    findings_by_component=findings_by_component,
                    title=f"AI Topology — {project_id} ({environment})",
                    environment=environment,
                )
            except Exception as exc:
                logger.warning("Failed to generate topology diagram: %s", exc)

        return diagrams

    # ----- public helpers -----

    @staticmethod
    def list_available_analyzers() -> list[str]:
        """Return names of all available analyzers."""
        return list(AVAILABLE_ANALYZERS.keys())

    @staticmethod
    def get_analyzer_info() -> list[dict[str, str]]:
        """Return info about available analyzers."""
        info = {
            "context": "Scans system prompts, CLAUDE.md, .cursorrules for injection/exfiltration patterns",
            "mcp": "Checks MCP server configs for injection, exfiltration, privilege escalation, rugpull",
            "workflow": "Detects LangChain/CrewAI/AutoGen/LangGraph patterns, analyzes agent routing",
            "attack_surface": "Maps attack vectors and vulnerability paths through AI system",
            "rag": "Checks knowledge bases, vector stores for poisoning risks",
            "model_file": "Checks .pt/.gguf/.bin/.safetensors for embedded code, poisoning",
        }
        return [
            {"name": name, "description": info.get(name, ""), "module": path}
            for name, path in AVAILABLE_ANALYZERS.items()
        ]
