"""Guardrail definitions for AI security boundaries.

Guardrails define security boundaries and constraints that
should be enforced to protect AI deployments.
"""

from dataclasses import dataclass, field
from typing import Any

from pearl.scanning.types import AttackCategory, GuardrailSeverity, GuardrailType


@dataclass
class Guardrail:
    """A security guardrail definition."""

    id: str
    name: str
    description: str
    guardrail_type: GuardrailType
    severity: GuardrailSeverity

    # Implementation guidance
    implementation_steps: list[str] = field(default_factory=list)
    code_examples: dict[str, str] = field(default_factory=dict)  # language -> code
    configuration_examples: dict[str, str] = field(default_factory=dict)

    # Mapping to findings
    mitigates_categories: list[AttackCategory] = field(default_factory=list)
    required_for_compliance: list[str] = field(default_factory=list)  # Framework IDs

    # Metadata
    effort: str = "medium"  # low, medium, high
    effectiveness: str = "high"  # low, medium, high
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.guardrail_type.value,
            "severity": self.severity.value,
            "implementation_steps": self.implementation_steps,
            "code_examples": self.code_examples,
            "configuration_examples": self.configuration_examples,
            "mitigates": [c.value for c in self.mitigates_categories],
            "compliance": self.required_for_compliance,
            "effort": self.effort,
            "effectiveness": self.effectiveness,
            "tags": self.tags,
        }


class GuardrailRegistry:
    """Registry of available guardrails."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._guardrails: dict[str, Guardrail] = {}
        self._by_type: dict[GuardrailType, list[Guardrail]] = {}
        self._by_category: dict[AttackCategory, list[Guardrail]] = {}

    def register(self, guardrail: Guardrail) -> None:
        """Register a guardrail."""
        self._guardrails[guardrail.id] = guardrail

        # Index by type
        if guardrail.guardrail_type not in self._by_type:
            self._by_type[guardrail.guardrail_type] = []
        self._by_type[guardrail.guardrail_type].append(guardrail)

        # Index by category
        for category in guardrail.mitigates_categories:
            if category not in self._by_category:
                self._by_category[category] = []
            self._by_category[category].append(guardrail)

    def get(self, guardrail_id: str) -> Guardrail | None:
        """Get guardrail by ID."""
        return self._guardrails.get(guardrail_id)

    def get_by_type(self, guardrail_type: GuardrailType) -> list[Guardrail]:
        """Get guardrails by type."""
        return self._by_type.get(guardrail_type, [])

    def get_for_category(self, category: AttackCategory) -> list[Guardrail]:
        """Get guardrails that mitigate a category."""
        return self._by_category.get(category, [])

    def get_all(self) -> list[Guardrail]:
        """Get all registered guardrails."""
        return list(self._guardrails.values())

    def get_by_severity(self, severity: GuardrailSeverity) -> list[Guardrail]:
        """Get guardrails by severity."""
        return [g for g in self._guardrails.values() if g.severity == severity]


def get_default_guardrails() -> GuardrailRegistry:
    """Get registry with default guardrails."""
    registry = GuardrailRegistry()

    # 1. Prompt Injection Blocking
    registry.register(Guardrail(
        id="grd-input-sanitize",
        name="Prompt Injection Blocking",
        description=(
            "Intercept user prompts at the proxy layer and block known injection "
            "patterns before they reach the model."
        ),
        guardrail_type=GuardrailType.INPUT_VALIDATION,
        severity=GuardrailSeverity.CRITICAL,
        implementation_steps=[
            "Deploy a pre-processing middleware in the API gateway that runs before model inference",
            "Build a deny-list of high-signal injection phrases and reject on match",
            "Add a lightweight classifier scored 0-1 for injection likelihood; block above threshold",
            "Separate the system prompt from user input with enforced delimiter tokens",
            "Return a structured 422 response with a violation code for SIEM tracking",
        ],
        code_examples={
            "python": (
                "import re\n"
                "from fastapi import Request, HTTPException\n"
                "\n"
                "INJECTION_PATTERNS = [\n"
                '    r"(?i)ignore\\s+(all\\s+)?(previous|prior)\\s+(instructions|prompts)",\n'
                '    r"(?i)you\\s+are\\s+now\\s+(a|an|the|DAN)",\n'
                '    r"(?i)disregard\\s+(all|your)\\s+(rules|instructions)",\n'
                "]\n"
                "_COMPILED = [re.compile(p) for p in INJECTION_PATTERNS]\n"
                "\n"
                "async def injection_guard(request: Request):\n"
                '    body = await request.json()\n'
                '    user_text = body.get("prompt", "")\n'
                "    for pattern in _COMPILED:\n"
                "        if pattern.search(user_text):\n"
                "            raise HTTPException(422, detail={\"violation\": \"prompt_injection\"})\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.PROMPT_INJECTION,
            AttackCategory.JAILBREAK,
        ],
        required_for_compliance=["LLM01", "AML.T0015"],
        effort="medium",
        effectiveness="high",
        tags=["prompt-injection", "input-validation", "proxy"],
    ))

    # 2. Content Moderation Filter
    registry.register(Guardrail(
        id="grd-content-filter",
        name="Content Moderation Filter",
        description=(
            "Classify and block harmful, toxic, or policy-violating content in "
            "both model inputs and outputs at the proxy layer."
        ),
        guardrail_type=GuardrailType.CONTENT_MODERATION,
        severity=GuardrailSeverity.HIGH,
        implementation_steps=[
            "Integrate a content-classification model as a sidecar or middleware",
            "Define category thresholds (violence, sexual, self-harm) tunable via config",
            "Apply classification to both the incoming prompt and the model response",
            "Return a 451 status with the category and confidence on block",
            "Add an allow-list bypass for authorized red-team roles gated behind RBAC",
        ],
        code_examples={
            "python": (
                "import httpx\n"
                "\n"
                "async def moderate_text(text: str, api_key: str) -> dict:\n"
                '    async with httpx.AsyncClient() as client:\n'
                "        resp = await client.post(\n"
                '            "https://api.openai.com/v1/moderations",\n'
                '            headers={"Authorization": f"Bearer {api_key}"},\n'
                '            json={"input": text},\n'
                "        )\n"
                '        return resp.json()["results"][0]\n'
            ),
        },
        mitigates_categories=[
            AttackCategory.TOXICITY,
            AttackCategory.IMPROPER_OUTPUT,
            AttackCategory.JAILBREAK,
        ],
        required_for_compliance=["LLM05"],
        effort="medium",
        effectiveness="medium",
        tags=["content-moderation", "safety", "proxy"],
    ))

    # 3. PII Output Filtering
    registry.register(Guardrail(
        id="grd-output-pii",
        name="PII & Sensitive Data Filtering",
        description=(
            "Scan model outputs for personally identifiable information and "
            "redact before the response reaches the client."
        ),
        guardrail_type=GuardrailType.OUTPUT_FILTERING,
        severity=GuardrailSeverity.CRITICAL,
        implementation_steps=[
            "Implement a post-inference filter that regex-scans every model response",
            "Define PII patterns: SSN, credit card, email, phone, AWS keys, JWT tokens",
            "Replace matches with typed redaction tokens like [REDACTED_SSN]",
            "Ship redaction events to SIEM with pattern type and request context",
            "Maintain an allow-list for known-safe patterns to reduce false positives",
        ],
        code_examples={
            "python": (
                "import re\n"
                "\n"
                "PII_RULES = [\n"
                '    ("SSN", re.compile(r"\\b\\d{3}-\\d{2}-\\d{4}\\b")),\n'
                '    ("EMAIL", re.compile(r"\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b")),\n'
                '    ("AWS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),\n'
                "]\n"
                "\n"
                "def redact_pii(text: str) -> str:\n"
                "    for pii_type, pattern in PII_RULES:\n"
                '        text = pattern.sub(f"[REDACTED_{pii_type}]", text)\n'
                "    return text\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.SENSITIVE_INFO,
            AttackCategory.DATA_LEAKAGE,
        ],
        required_for_compliance=["LLM02"],
        effort="medium",
        effectiveness="high",
        tags=["pii-protection", "data-leakage", "privacy", "proxy"],
    ))

    # 4. Secret/Credential Detection
    registry.register(Guardrail(
        id="grd-output-secrets",
        name="Secret & Credential Detection",
        description=(
            "Detect API keys, tokens, passwords, and connection strings in model "
            "responses and block the output before delivery."
        ),
        guardrail_type=GuardrailType.OUTPUT_FILTERING,
        severity=GuardrailSeverity.CRITICAL,
        implementation_steps=[
            "Add a post-inference scanning step using regex and entropy analysis",
            "Cover common secret formats: AWS, GitHub, Slack, Stripe, and high-entropy strings",
            "Replace the entire response with a safe error message on detection",
            "Alert the security team immediately on credential-class detections",
        ],
        code_examples={
            "python": (
                "import math\n"
                "import re\n"
                "\n"
                "SECRET_PATTERNS = {\n"
                '    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),\n'
                '    "github_token": re.compile(r"gh[ps]_[A-Za-z0-9_]{36,}"),\n'
                '    "private_key": re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),\n'
                "}\n"
                "\n"
                "def scan_for_secrets(text: str) -> list[str]:\n"
                "    found = []\n"
                "    for name, pattern in SECRET_PATTERNS.items():\n"
                "        if pattern.search(text):\n"
                "            found.append(name)\n"
                "    return found\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.SECRETS_EXPOSURE,
            AttackCategory.DATA_LEAKAGE,
        ],
        required_for_compliance=["LLM02"],
        effort="medium",
        effectiveness="high",
        tags=["secrets-protection", "credential-leak", "proxy"],
    ))

    # 5. Tool/Function Call Restriction
    registry.register(Guardrail(
        id="grd-tool-restrict",
        name="Tool & Function Call Restriction",
        description=(
            "Restrict which tools and external APIs the model may invoke by "
            "enforcing an allow-list at the proxy layer."
        ),
        guardrail_type=GuardrailType.ACCESS_CONTROL,
        severity=GuardrailSeverity.HIGH,
        implementation_steps=[
            "Define a tool allow-list specifying exactly which function names the model may call",
            "Validate tool call arguments against JSON schemas before forwarding",
            "Implement call-frequency limits per tool to prevent resource abuse loops",
            "Log every tool invocation with full arguments and user ID for audit",
            "Require human-in-the-loop confirmation for destructive operations",
        ],
        code_examples={
            "python": (
                "TOOL_POLICY = {\n"
                '    "search": {"allowed": True, "max_calls": 5},\n'
                '    "execute_code": {"allowed": False},\n'
                "}\n"
                "\n"
                "def validate_tool_call(tool_name: str) -> str | None:\n"
                "    policy = TOOL_POLICY.get(tool_name)\n"
                "    if policy is None:\n"
                "        return f\"Tool '{tool_name}' not registered\"\n"
                '    if not policy.get("allowed", False):\n'
                "        return f\"Tool '{tool_name}' blocked by policy\"\n"
                "    return None\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.EXCESSIVE_AGENCY,
            AttackCategory.PRIVILEGE_ESCALATION,
        ],
        required_for_compliance=["LLM06"],
        effort="medium",
        effectiveness="high",
        tags=["tool-restriction", "excessive-agency", "proxy"],
    ))

    # 6. Request Rate Limiting
    registry.register(Guardrail(
        id="grd-rate-limit",
        name="Request Rate Limiting",
        description=(
            "Enforce per-user, per-IP, and per-API-key rate limits at the proxy "
            "to prevent denial-of-service and brute-force extraction attacks."
        ),
        guardrail_type=GuardrailType.RATE_LIMITING,
        severity=GuardrailSeverity.MEDIUM,
        implementation_steps=[
            "Configure tiered rate limits using sliding window counters in Redis",
            "Add token-based limits to prevent cost-runaway from long-response attacks",
            "Return HTTP 429 with Retry-After header and JSON error body",
        ],
        code_examples={
            "python": (
                "import time\n"
                "\n"
                "class SlidingWindowLimiter:\n"
                "    def __init__(self):\n"
                "        self._windows: dict[str, list[float]] = {}\n"
                "\n"
                "    def check(self, key: str, limit: int, window_sec: int) -> bool:\n"
                "        now = time.time()\n"
                "        entries = self._windows.setdefault(key, [])\n"
                "        entries[:] = [t for t in entries if t > now - window_sec]\n"
                "        if len(entries) >= limit:\n"
                "            return False\n"
                "        entries.append(now)\n"
                "        return True\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.UNBOUNDED_CONSUMPTION,
            AttackCategory.DENIAL_OF_SERVICE,
        ],
        required_for_compliance=["LLM10"],
        effort="low",
        effectiveness="high",
        tags=["rate-limiting", "dos-protection", "proxy"],
    ))

    # 7. Token Length Limits
    registry.register(Guardrail(
        id="grd-input-length",
        name="Input & Output Token Limits",
        description=(
            "Enforce hard limits on input prompt length and output token count "
            "to prevent context-overflow attacks and cost runaway."
        ),
        guardrail_type=GuardrailType.RESOURCE_LIMITS,
        severity=GuardrailSeverity.MEDIUM,
        implementation_steps=[
            "Set max_input_tokens and max_output_tokens based on the model's context window",
            "Implement fast token-counting in the proxy to reject oversized inputs",
            "Cap max_tokens in the forwarded API call body even if the client requests more",
        ],
        code_examples={
            "python": (
                "MAX_INPUT_TOKENS = 8192\n"
                "MAX_OUTPUT_TOKENS = 4096\n"
                "\n"
                "def enforce_token_limits(body: dict) -> dict:\n"
                '    requested = body.get("max_tokens", MAX_OUTPUT_TOKENS)\n'
                '    body["max_tokens"] = min(requested, MAX_OUTPUT_TOKENS)\n'
                "    return body\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.UNBOUNDED_CONSUMPTION,
            AttackCategory.DENIAL_OF_SERVICE,
        ],
        required_for_compliance=["LLM10"],
        effort="low",
        effectiveness="high",
        tags=["token-limits", "dos-protection", "cost-control", "proxy"],
    ))

    # 8. Role-Based Access Control
    registry.register(Guardrail(
        id="grd-rbac",
        name="Role-Based Access Control",
        description=(
            "Enforce RBAC at the proxy layer so model access and tool permissions "
            "are scoped to the caller's role."
        ),
        guardrail_type=GuardrailType.ACCESS_CONTROL,
        severity=GuardrailSeverity.HIGH,
        implementation_steps=[
            "Define roles with explicit permission sets covering model access and tool allow-lists",
            "Validate the caller's role from the JWT/session at the proxy before forwarding",
            "Gate destructive tool calls behind admin or power_user roles",
            "Log role-based decisions to the audit trail for compliance reporting",
        ],
        code_examples={
            "python": (
                "from enum import Enum\n"
                "\n"
                "class Role(Enum):\n"
                '    USER = "user"\n'
                '    ADMIN = "admin"\n'
                '    RED_TEAM = "red_team"\n'
                "\n"
                "ROLE_TOOLS: dict[Role, set[str]] = {\n"
                '    Role.USER: {"search", "get_weather"},\n'
                '    Role.ADMIN: {"*"},\n'
                '    Role.RED_TEAM: {"*"},\n'
                "}\n"
                "\n"
                "def check_access(role: Role, tool: str) -> bool:\n"
                '    allowed = ROLE_TOOLS.get(role, set())\n'
                '    return "*" in allowed or tool in allowed\n'
            ),
        },
        mitigates_categories=[
            AttackCategory.EXCESSIVE_AGENCY,
            AttackCategory.PRIVILEGE_ESCALATION,
        ],
        required_for_compliance=["LLM06"],
        effort="medium",
        effectiveness="high",
        tags=["rbac", "access-control", "proxy"],
    ))

    # 9. TLS 1.3 Enforcement
    registry.register(Guardrail(
        id="grd-encrypt-transit",
        name="TLS 1.3 Enforcement",
        description=(
            "Enforce TLS 1.3 on all proxy-to-model and client-to-proxy connections "
            "to protect data in transit."
        ),
        guardrail_type=GuardrailType.NETWORK_SEGMENTATION,
        severity=GuardrailSeverity.HIGH,
        implementation_steps=[
            "Configure the proxy to terminate TLS 1.3 with strong cipher suites",
            "Disable TLS 1.0, 1.1, and 1.2 on all model-serving endpoints",
            "Enable HSTS with a 1-year max-age and includeSubDomains",
        ],
        code_examples={
            "python": (
                "import ssl\n"
                "\n"
                "def create_tls_context() -> ssl.SSLContext:\n"
                "    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)\n"
                "    ctx.minimum_version = ssl.TLSVersion.TLSv1_3\n"
                "    ctx.maximum_version = ssl.TLSVersion.TLSv1_3\n"
                "    return ctx\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.SENSITIVE_INFO,
            AttackCategory.DATA_LEAKAGE,
        ],
        required_for_compliance=["MANAGE-1"],
        effort="low",
        effectiveness="high",
        tags=["encryption", "tls", "data-protection", "proxy"],
    ))

    # 10. Direct Model Access Prevention
    registry.register(Guardrail(
        id="grd-model-access",
        name="Direct Model Access Prevention",
        description=(
            "Prevent direct access to model weights and inference internals by "
            "ensuring the proxy is the only path to the model."
        ),
        guardrail_type=GuardrailType.MODEL_PROTECTION,
        severity=GuardrailSeverity.MEDIUM,
        implementation_steps=[
            "Place model inference servers in a private subnet with no public IP",
            "Block model metadata endpoints from external access",
            "Enforce output-only access: clients send prompts but cannot download weights",
            "Implement request signing between proxy and inference server",
            "Monitor for model extraction patterns indicating distillation attempts",
        ],
        code_examples={
            "python": (
                "# Network policy: only proxy can reach the inference server\n"
                "ALLOWED_INFERENCE_CALLERS = {\"10.0.1.0/24\"}  # proxy subnet\n"
                "\n"
                "def is_allowed_caller(ip: str) -> bool:\n"
                "    import ipaddress\n"
                "    addr = ipaddress.ip_address(ip)\n"
                "    return any(\n"
                "        addr in ipaddress.ip_network(net)\n"
                "        for net in ALLOWED_INFERENCE_CALLERS\n"
                "    )\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.MODEL_THEFT,
            AttackCategory.SUPPLY_CHAIN,
        ],
        required_for_compliance=["AML.T0040"],
        effort="medium",
        effectiveness="high",
        tags=["model-protection", "network-segmentation", "proxy"],
    ))

    # 11. Comprehensive Audit Logging
    registry.register(Guardrail(
        id="grd-audit-log",
        name="Comprehensive Audit Logging",
        description=(
            "Log every proxy decision in a structured, tamper-evident format "
            "for compliance and forensics."
        ),
        guardrail_type=GuardrailType.AUDIT_LOGGING,
        severity=GuardrailSeverity.HIGH,
        implementation_steps=[
            "Emit structured JSON log lines for every request with timestamp, user_id, and action",
            "Include guardrail decisions: which rules fired, confidence scores, and block status",
            "Ship logs to an append-only store to prevent tampering",
            "Set up real-time alerting on high-severity events",
            "Never log the full prompt or response body in production; use hashes instead",
        ],
        code_examples={
            "python": (
                "import hashlib\n"
                "import json\n"
                "import logging\n"
                "import time\n"
                "from dataclasses import dataclass, field, asdict\n"
                "\n"
                "logger = logging.getLogger(\"audit\")\n"
                "\n"
                "@dataclass\n"
                "class AuditEvent:\n"
                "    timestamp: float = field(default_factory=time.time)\n"
                '    request_id: str = ""\n'
                '    user_id: str = ""\n'
                '    action: str = "allow"\n'
                '    reason: str = ""\n'
                "\n"
                "def log_audit_event(event: AuditEvent):\n"
                "    logger.info(json.dumps(asdict(event), default=str))\n"
            ),
        },
        mitigates_categories=[
            AttackCategory.PRIVILEGE_ESCALATION,
            AttackCategory.DATA_LEAKAGE,
        ],
        required_for_compliance=["GOVERN-1"],
        effort="medium",
        effectiveness="medium",
        tags=["audit", "logging", "compliance", "proxy"],
    ))

    return registry
