"""Policy templates for AI security configurations.

Pre-built policy templates that can be applied to AI deployments
based on security requirements and compliance needs.
"""

from dataclasses import dataclass, field
from typing import Any

from pearl.scanning.types import AttackCategory, PolicyCategory, ScanSeverity


@dataclass
class PolicyRule:
    """A single rule within a policy."""

    id: str
    name: str
    description: str
    condition: str  # Human-readable condition
    action: str  # What to do when condition is met
    severity: ScanSeverity = ScanSeverity.MEDIUM
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "condition": self.condition,
            "action": self.action,
            "severity": self.severity.value,
            "enabled": self.enabled,
        }


@dataclass
class PolicyTemplate:
    """A complete policy template."""

    id: str
    name: str
    description: str
    category: PolicyCategory
    version: str = "1.0.0"

    # Policy rules
    rules: list[PolicyRule] = field(default_factory=list)

    # Configuration
    config_schema: dict[str, Any] = field(default_factory=dict)
    default_config: dict[str, Any] = field(default_factory=dict)

    # Compliance mapping
    compliance_frameworks: list[str] = field(default_factory=list)
    mitigates: list[AttackCategory] = field(default_factory=list)

    # Metadata
    tags: list[str] = field(default_factory=list)
    recommended_for: list[str] = field(default_factory=list)  # Industries/use cases

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "version": self.version,
            "rules": [r.to_dict() for r in self.rules],
            "config_schema": self.config_schema,
            "default_config": self.default_config,
            "compliance_frameworks": self.compliance_frameworks,
            "mitigates": [m.value for m in self.mitigates],
            "tags": self.tags,
            "recommended_for": self.recommended_for,
        }


class PolicyRegistry:
    """Registry of policy templates."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._templates: dict[str, PolicyTemplate] = {}
        self._by_category: dict[PolicyCategory, list[PolicyTemplate]] = {}

    def register(self, template: PolicyTemplate) -> None:
        """Register a policy template."""
        self._templates[template.id] = template

        if template.category not in self._by_category:
            self._by_category[template.category] = []
        self._by_category[template.category].append(template)

    def get(self, template_id: str) -> PolicyTemplate | None:
        """Get template by ID."""
        return self._templates.get(template_id)

    def get_by_category(self, category: PolicyCategory) -> list[PolicyTemplate]:
        """Get templates by category."""
        return self._by_category.get(category, [])

    def get_all(self) -> list[PolicyTemplate]:
        """Get all templates."""
        return list(self._templates.values())

    def get_for_compliance(self, framework: str) -> list[PolicyTemplate]:
        """Get templates required for a compliance framework."""
        return [
            t
            for t in self._templates.values()
            if framework in t.compliance_frameworks
        ]


def get_policy_templates() -> PolicyRegistry:
    """Get registry with default policy templates."""
    registry = PolicyRegistry()

    # 1. Prompt Injection Defense (4 rules)
    registry.register(PolicyTemplate(
        id="pol-prompt-injection-defense",
        name="Prompt Injection Defense Policy",
        description="Comprehensive policy to prevent and detect prompt injection attacks.",
        category=PolicyCategory.PROMPT_SECURITY,
        rules=[
            PolicyRule(
                id="pi-sanitize-input",
                name="Sanitize User Input",
                description="All user inputs must be sanitized before model processing",
                condition="User input received",
                action="Apply input sanitization filter",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="pi-detect-patterns",
                name="Detect Injection Patterns",
                description="Block inputs containing known injection patterns",
                condition="Input matches injection pattern",
                action="Block request and log attempt",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="pi-separate-data",
                name="Separate Data from Instructions",
                description="Clearly separate user data from system instructions",
                condition="Building prompt with user data",
                action="Use delimiters and structured prompts",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="pi-output-validation",
                name="Validate Model Output",
                description="Validate outputs have not been manipulated by injection",
                condition="Model returns response",
                action="Check for unexpected behaviors",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "max_input_length": 4096,
            "block_on_detection": True,
            "log_attempts": True,
            "alert_threshold": 5,
        },
        compliance_frameworks=["owasp_llm", "mitre_atlas"],
        mitigates=[AttackCategory.PROMPT_INJECTION, AttackCategory.JAILBREAK],
        tags=["prompt-injection", "input-validation"],
        recommended_for=["chatbots", "assistants", "customer-facing"],
    ))

    # 2. Data Loss Prevention (4 rules)
    registry.register(PolicyTemplate(
        id="pol-data-loss-prevention",
        name="Data Loss Prevention Policy",
        description="Prevent sensitive data from being exposed through model interactions.",
        category=PolicyCategory.DATA_PROTECTION,
        rules=[
            PolicyRule(
                id="dlp-scan-output",
                name="Scan Output for Sensitive Data",
                description="Scan all model outputs for PII and sensitive data",
                condition="Model generates output",
                action="Apply DLP scanning",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="dlp-redact-pii",
                name="Redact PII",
                description="Automatically redact detected PII from outputs",
                condition="PII detected in output",
                action="Redact and log",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="dlp-block-secrets",
                name="Block Secret Exposure",
                description="Block outputs containing secrets or credentials",
                condition="Secret pattern detected",
                action="Block response completely",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="dlp-training-data",
                name="Protect Training Data",
                description="Prevent extraction of training data",
                condition="Extraction attempt detected",
                action="Block and alert",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "pii_types": ["ssn", "credit_card", "email", "phone", "address"],
            "secret_patterns": ["api_key", "password", "token", "secret"],
            "redaction_style": "mask",
            "alert_on_detection": True,
        },
        compliance_frameworks=["nist_ai_rmf", "owasp_llm"],
        mitigates=[
            AttackCategory.SENSITIVE_INFO,
            AttackCategory.DATA_LEAKAGE,
            AttackCategory.SECRETS_EXPOSURE,
        ],
        tags=["dlp", "pii", "secrets"],
        recommended_for=["healthcare", "finance", "enterprise"],
    ))

    # 3. Access Control (3 rules)
    registry.register(PolicyTemplate(
        id="pol-access-control",
        name="Least Privilege Access Policy",
        description="Enforce minimum necessary permissions for AI system access.",
        category=PolicyCategory.ACCESS_CONTROL,
        rules=[
            PolicyRule(
                id="ac-authenticate",
                name="Require Authentication",
                description="All requests must be authenticated",
                condition="Request received",
                action="Verify authentication token",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="ac-authorize",
                name="Check Authorization",
                description="Verify user has permission for requested action",
                condition="Authenticated request",
                action="Check RBAC permissions",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="ac-scope-limit",
                name="Limit Action Scope",
                description="Limit what actions the model can perform per role",
                condition="Model attempts action",
                action="Verify action is in allowed scope",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "auth_methods": ["jwt", "api_key"],
            "session_timeout_minutes": 30,
            "max_failed_attempts": 5,
        },
        compliance_frameworks=["nist_ai_rmf", "owasp_llm"],
        mitigates=[
            AttackCategory.PRIVILEGE_ESCALATION,
            AttackCategory.EXCESSIVE_AGENCY,
        ],
        tags=["authentication", "authorization", "rbac"],
        recommended_for=["enterprise", "regulated"],
    ))

    # 4. Model Security (3 rules)
    registry.register(PolicyTemplate(
        id="pol-model-security",
        name="Model Integrity Protection Policy",
        description="Protect model integrity from tampering and unauthorized modifications.",
        category=PolicyCategory.MODEL_SECURITY,
        rules=[
            PolicyRule(
                id="ms-verify-source",
                name="Verify Model Source",
                description="Verify models come from trusted sources",
                condition="Model loaded",
                action="Check signature and provenance",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="ms-safe-format",
                name="Use Safe Model Formats",
                description="Only use safe serialization formats (reject pickle)",
                condition="Loading model file",
                action="Reject unsafe formats",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="ms-hash-verify",
                name="Verify Model Hash",
                description="Verify model file integrity via cryptographic hash",
                condition="Before model use",
                action="Compare hash to known good value",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "allowed_formats": ["safetensors", "onnx", "gguf"],
            "blocked_formats": ["pickle", "pkl", "pt", "pth"],
            "require_signature": True,
        },
        compliance_frameworks=["mitre_atlas", "nist_ai_rmf"],
        mitigates=[
            AttackCategory.SUPPLY_CHAIN,
            AttackCategory.DATA_MODEL_POISONING,
        ],
        tags=["model-integrity", "supply-chain"],
        recommended_for=["production", "high-security"],
    ))

    # 5. Infrastructure Security (3 rules)
    registry.register(PolicyTemplate(
        id="pol-infrastructure-security",
        name="Secure Deployment Policy",
        description="Security requirements for AI deployment infrastructure.",
        category=PolicyCategory.INFRASTRUCTURE,
        rules=[
            PolicyRule(
                id="inf-network-isolation",
                name="Network Isolation",
                description="Isolate AI workloads from general network",
                condition="Deployment configuration",
                action="Enforce network segmentation",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="inf-no-privileged",
                name="No Privileged Containers",
                description="Containers must not run in privileged mode",
                condition="Container deployment",
                action="Reject privileged containers",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="inf-resource-limits",
                name="Enforce Resource Limits",
                description="All deployments must have memory and CPU limits",
                condition="Deployment configuration",
                action="Require resource limits",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "require_tls": True,
            "min_tls_version": "1.3",
            "max_memory_gb": 16,
            "max_cpu_cores": 8,
        },
        compliance_frameworks=["nist_ai_rmf", "owasp_llm"],
        mitigates=[
            AttackCategory.PRIVILEGE_ESCALATION,
            AttackCategory.DENIAL_OF_SERVICE,
        ],
        tags=["infrastructure", "containers", "kubernetes"],
        recommended_for=["cloud", "kubernetes", "production"],
    ))

    # 6. Compliance Monitoring (3 rules)
    registry.register(PolicyTemplate(
        id="pol-compliance-monitoring",
        name="Compliance Monitoring Policy",
        description="Continuous monitoring to ensure ongoing compliance with AI security frameworks.",
        category=PolicyCategory.COMPLIANCE,
        rules=[
            PolicyRule(
                id="cm-periodic-scan",
                name="Periodic Compliance Scans",
                description="Run automated compliance scans on a regular schedule",
                condition="Scan schedule triggered",
                action="Execute compliance scan and report results",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="cm-drift-detection",
                name="Compliance Drift Detection",
                description="Detect when configurations drift from compliant state",
                condition="Configuration change detected",
                action="Compare against compliance baseline and alert on drift",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="cm-evidence-collection",
                name="Evidence Collection",
                description="Automatically collect and store compliance evidence",
                condition="Compliance-relevant event occurs",
                action="Archive evidence with timestamp and chain of custody",
                severity=ScanSeverity.MEDIUM,
            ),
        ],
        default_config={
            "scan_frequency": "weekly",
            "frameworks": ["owasp_llm", "nist_ai_rmf"],
            "alert_on_non_compliant": True,
            "evidence_retention_days": 365,
        },
        compliance_frameworks=["owasp_llm", "nist_ai_rmf", "eu_ai_act"],
        mitigates=[
            AttackCategory.SUPPLY_CHAIN,
            AttackCategory.EXCESSIVE_AGENCY,
        ],
        tags=["compliance", "monitoring", "audit"],
        recommended_for=["enterprise", "regulated", "finance"],
    ))

    # 7. Monitoring & Logging (3 rules)
    registry.register(PolicyTemplate(
        id="pol-monitoring-logging",
        name="Security Monitoring Policy",
        description="Requirements for monitoring AI systems for security events.",
        category=PolicyCategory.MONITORING,
        rules=[
            PolicyRule(
                id="ml-log-requests",
                name="Log All Requests",
                description="Log all inference requests for audit",
                condition="Request processed",
                action="Write to secure log",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="ml-detect-anomalies",
                name="Detect Anomalies",
                description="Monitor for anomalous usage patterns",
                condition="Continuous monitoring",
                action="Alert on anomalies",
                severity=ScanSeverity.MEDIUM,
            ),
            PolicyRule(
                id="ml-alert-violations",
                name="Alert on Policy Violations",
                description="Immediate alerts for security policy violations",
                condition="Policy violation detected",
                action="Send alert to security team",
                severity=ScanSeverity.CRITICAL,
            ),
        ],
        default_config={
            "log_retention_days": 90,
            "alert_channels": ["email", "slack"],
            "anomaly_threshold": 2.0,
            "sample_rate": 1.0,
        },
        compliance_frameworks=["nist_ai_rmf", "owasp_llm"],
        mitigates=[
            AttackCategory.PRIVILEGE_ESCALATION,
            AttackCategory.DATA_LEAKAGE,
        ],
        tags=["monitoring", "logging", "alerting"],
        recommended_for=["enterprise", "regulated", "production"],
    ))

    # 8. Incident Response (3 rules)
    registry.register(PolicyTemplate(
        id="pol-incident-response",
        name="AI Security Incident Response Policy",
        description="Procedures for responding to AI security incidents.",
        category=PolicyCategory.INCIDENT_RESPONSE,
        rules=[
            PolicyRule(
                id="ir-classify",
                name="Classify Incident",
                description="Classify incidents by severity and type",
                condition="Incident detected",
                action="Apply classification matrix",
                severity=ScanSeverity.HIGH,
            ),
            PolicyRule(
                id="ir-contain",
                name="Contain Incident",
                description="Immediately contain the incident to prevent spread",
                condition="High severity incident",
                action="Isolate affected systems",
                severity=ScanSeverity.CRITICAL,
            ),
            PolicyRule(
                id="ir-notify",
                name="Notify Stakeholders",
                description="Notify appropriate stakeholders per escalation matrix",
                condition="Incident classified",
                action="Send notifications per escalation matrix",
                severity=ScanSeverity.HIGH,
            ),
        ],
        default_config={
            "escalation_matrix": {
                "critical": ["security_lead", "ciso", "legal"],
                "high": ["security_lead", "engineering_lead"],
                "medium": ["security_team"],
                "low": ["on_call"],
            },
            "containment_actions": ["disable_endpoint", "revoke_tokens", "isolate_network"],
            "notification_sla_minutes": {"critical": 15, "high": 60, "medium": 240},
        },
        compliance_frameworks=["nist_ai_rmf", "owasp_llm"],
        mitigates=[
            AttackCategory.DATA_LEAKAGE,
            AttackCategory.PRIVILEGE_ESCALATION,
        ],
        tags=["incident-response", "security-operations"],
        recommended_for=["enterprise", "regulated"],
    ))

    return registry
