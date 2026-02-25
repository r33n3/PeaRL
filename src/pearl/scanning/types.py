"""Scanning type definitions for PeaRL.

Enums for attack categories, component types, severity levels,
compliance frameworks, agentic frameworks, guardrail types,
and policy categories used by the scanning subsystem.
"""

from enum import StrEnum


class AttackCategory(StrEnum):
    """Attack and vulnerability categories.

    Aligned with OWASP LLM Top 10 2025 and extended with
    additional categories for comprehensive coverage.
    """

    # OWASP LLM Top 10 2025
    PROMPT_INJECTION = "prompt_injection"
    SENSITIVE_INFO = "sensitive_info"
    SUPPLY_CHAIN = "supply_chain"
    DATA_MODEL_POISONING = "data_model_poisoning"
    IMPROPER_OUTPUT = "improper_output"
    EXCESSIVE_AGENCY = "excessive_agency"
    SYSTEM_PROMPT_LEAKAGE = "system_prompt_leakage"
    VECTOR_EMBEDDING = "vector_embedding"
    MISINFORMATION = "misinformation"
    UNBOUNDED_CONSUMPTION = "unbounded_consumption"

    # Extended categories
    JAILBREAK = "jailbreak"
    DATA_LEAKAGE = "data_leakage"
    HALLUCINATION = "hallucination"
    BIAS = "bias"
    TOXICITY = "toxicity"
    SECRETS_EXPOSURE = "secrets_exposure"
    INSECURE_PLUGIN = "insecure_plugin"
    MODEL_THEFT = "model_theft"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DENIAL_OF_SERVICE = "denial_of_service"


class ComponentType(StrEnum):
    """Deployment component types."""

    MODEL = "model"
    CONTEXT = "context"
    MCP_SERVER = "mcp_server"
    SKILL = "skill"
    KNOWLEDGE = "knowledge"
    CODE = "code"
    CONFIG = "config"
    INFRASTRUCTURE = "infrastructure"
    WORKFLOW = "workflow"
    MEMORY = "memory"
    GUARDRAILS = "guardrails"


class ScanSeverity(StrEnum):
    """Finding severity classification.

    Named ScanSeverity to avoid collision with PeaRL's existing RiskLevel.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FrameworkType(StrEnum):
    """Compliance framework types."""

    OWASP_LLM = "owasp_llm"
    MITRE_ATLAS = "mitre_atlas"
    NIST_AI_RMF = "nist_ai_rmf"
    EU_AI_ACT = "eu_ai_act"


class AgenticFramework(StrEnum):
    """Supported agentic AI frameworks."""

    LANGCHAIN = "langchain"
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"
    AUTOGEN = "autogen"
    OPENAI_AGENTS = "openai_agents"
    SEMANTIC_KERNEL = "semantic_kernel"
    HAYSTACK = "haystack"
    LLAMAINDEX = "llamaindex"
    CUSTOM = "custom"


class GuardrailType(StrEnum):
    """Types of guardrails."""

    INPUT_VALIDATION = "input_validation"
    OUTPUT_FILTERING = "output_filtering"
    RATE_LIMITING = "rate_limiting"
    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    MODEL_PROTECTION = "model_protection"
    AUDIT_LOGGING = "audit_logging"
    CONTENT_MODERATION = "content_moderation"
    RESOURCE_LIMITS = "resource_limits"
    NETWORK_SEGMENTATION = "network_segmentation"


class GuardrailSeverity(StrEnum):
    """Severity if guardrail is violated."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ADVISORY = "advisory"


class PolicyCategory(StrEnum):
    """Categories of security policies."""

    PROMPT_SECURITY = "prompt_security"
    DATA_PROTECTION = "data_protection"
    ACCESS_CONTROL = "access_control"
    MODEL_SECURITY = "model_security"
    INFRASTRUCTURE = "infrastructure"
    COMPLIANCE = "compliance"
    MONITORING = "monitoring"
    INCIDENT_RESPONSE = "incident_response"


class RequirementStatus(StrEnum):
    """Status of a compliance requirement."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"
    NOT_ASSESSED = "not_assessed"
