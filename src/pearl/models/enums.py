"""String enums derived from PeaRL JSON Schema definitions."""

from enum import StrEnum


class Environment(StrEnum):
    SANDBOX = "sandbox"
    DEV = "dev"
    PREPROD = "preprod"
    PROD = "prod"


class DeliveryStage(StrEnum):
    BOOTSTRAP = "bootstrap"
    PROTOTYPE = "prototype"
    PILOT = "pilot"
    HARDENING = "hardening"
    PREPROD = "preprod"
    PROD = "prod"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class AutonomyMode(StrEnum):
    ASSISTIVE = "assistive"
    SUPERVISED_AUTONOMOUS = "supervised_autonomous"
    DELEGATED_AUTONOMOUS = "delegated_autonomous"
    READ_ONLY = "read_only"


class TrustLabel(StrEnum):
    TRUSTED_INTERNAL = "trusted_internal"
    TRUSTED_EXTERNAL_REGISTERED = "trusted_external_registered"
    UNTRUSTED_EXTERNAL = "untrusted_external"
    MANUAL_UNVERIFIED = "manual_unverified"


class BusinessCriticality(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    MISSION_CRITICAL = "mission_critical"


class ExternalExposure(StrEnum):
    INTERNAL_ONLY = "internal_only"
    PARTNER = "partner"
    CUSTOMER_FACING = "customer_facing"
    PUBLIC = "public"


class HashAlgorithm(StrEnum):
    SHA256 = "sha256"
    SHA512 = "sha512"


class ReferenceKind(StrEnum):
    API = "api"
    SCHEMA = "schema"
    ARTIFACT = "artifact"
    FINDING = "finding"
    APPROVAL = "approval"
    EXCEPTION = "exception"
    REPORT = "report"
    DOC = "doc"


class ToolType(StrEnum):
    SAST = "sast"
    DAST = "dast"
    SCA = "sca"
    CSPM = "cspm"
    CNAPP = "cnapp"
    CIEM = "ciem"
    API_SECURITY = "api_security"
    RUNTIME = "runtime"
    GOVERNANCE = "governance"
    THREAT_MODEL = "threat_model"
    RAI_MONITOR = "rai_monitor"
    MANUAL = "manual"
    MASS = "mass"
    FEU = "feu"


class FindingCategory(StrEnum):
    SECURITY = "security"
    RESPONSIBLE_AI = "responsible_ai"
    GOVERNANCE = "governance"
    ARCHITECTURE_DRIFT = "architecture_drift"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Exploitability(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskType(StrEnum):
    FEATURE = "feature"
    FIX = "fix"
    REMEDIATION = "remediation"
    REFACTOR = "refactor"
    CONFIG = "config"
    POLICY = "policy"


class JobType(StrEnum):
    COMPILE_CONTEXT = "compile_context"
    PLANNING_BUNDLE = "planning_bundle"
    NORMALIZE_FINDINGS = "normalize_findings"
    GENERATE_REMEDIATION_SPEC = "generate_remediation_spec"
    REPORT = "report"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class ApprovalRequestType(StrEnum):
    DEPLOYMENT_GATE = "deployment_gate"
    AUTH_FLOW_CHANGE = "auth_flow_change"
    NETWORK_POLICY_CHANGE = "network_policy_change"
    EXCEPTION = "exception"
    REMEDIATION_EXECUTION = "remediation_execution"
    PROMOTION_GATE = "promotion_gate"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    NEEDS_INFO = "needs_info"


class ApprovalDecisionValue(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ExceptionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REJECTED = "rejected"


class ApprovalLevel(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    ELEVATED = "elevated"
    HIGH = "high"
    STRICT = "strict"


class RemediationEligibility(StrEnum):
    AUTO_ALLOWED = "auto_allowed"
    AUTO_ALLOWED_WITH_APPROVAL = "auto_allowed_with_approval"
    HUMAN_REQUIRED = "human_required"
    NOT_AUTONOMOUS = "not_autonomous"


class ReportType(StrEnum):
    RELEASE_READINESS = "release_readiness"
    RESIDUAL_RISK = "residual_risk"
    CONTROL_COVERAGE = "control_coverage"
    FINDINGS_TREND = "findings_trend"
    RAI_POSTURE = "rai_posture"
    ENVIRONMENT_POSTURE = "environment_posture"


class ReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"


# --- Promotion Gate Enums ---


class GateRuleType(StrEnum):
    # Traditional security rules
    PROJECT_REGISTERED = "project_registered"
    ORG_BASELINE_ATTACHED = "org_baseline_attached"
    APP_SPEC_DEFINED = "app_spec_defined"
    NO_HARDCODED_SECRETS = "no_hardcoded_secrets"
    UNIT_TESTS_EXIST = "unit_tests_exist"
    UNIT_TEST_COVERAGE = "unit_test_coverage"
    INTEGRATION_TEST_COVERAGE = "integration_test_coverage"
    SECURITY_BASELINE_TESTS = "security_baseline_tests"
    CRITICAL_FINDINGS_ZERO = "critical_findings_zero"
    HIGH_FINDINGS_ZERO = "high_findings_zero"
    DATA_CLASSIFICATIONS_DOCUMENTED = "data_classifications_documented"
    IAM_ROLES_DEFINED = "iam_roles_defined"
    NETWORK_BOUNDARIES_DECLARED = "network_boundaries_declared"
    ALL_CONTROLS_VERIFIED = "all_controls_verified"
    SECURITY_REVIEW_APPROVAL = "security_review_approval"
    EXEC_SPONSOR_APPROVAL = "exec_sponsor_approval"
    RESIDUAL_RISK_REPORT = "residual_risk_report"
    READ_ONLY_AUTONOMY = "read_only_autonomy"
    # Scan target rules
    SCAN_TARGET_REGISTERED = "scan_target_registered"
    # MASS-sourced AI security rules
    MASS_SCAN_COMPLETED = "mass_scan_completed"
    NO_PROMPT_INJECTION = "no_prompt_injection"
    GUARDRAILS_VERIFIED = "guardrails_verified"
    NO_PII_LEAKAGE = "no_pii_leakage"
    OWASP_LLM_TOP10_CLEAR = "owasp_llm_top10_clear"
    MASS_RISK_ACCEPTABLE = "mass_risk_acceptable"
    COMPREHENSIVE_MASS_SCAN = "comprehensive_mass_scan"
    RAI_EVAL_COMPLETED = "rai_eval_completed"
    MODEL_CARD_DOCUMENTED = "model_card_documented"
    # FEU-sourced fairness rules
    FAIRNESS_CASE_DEFINED = "fairness_case_defined"
    FAIRNESS_REQUIREMENTS_MET = "fairness_requirements_met"
    FAIRNESS_EVIDENCE_CURRENT = "fairness_evidence_current"
    FAIRNESS_ATTESTATION_SIGNED = "fairness_attestation_signed"
    FAIRNESS_HARD_BLOCKS_CLEAR = "fairness_hard_blocks_clear"
    FAIRNESS_DRIFT_ACCEPTABLE = "fairness_drift_acceptable"
    FAIRNESS_CONTEXT_RECEIPT_VALID = "fairness_context_receipt_valid"
    FAIRNESS_EXCEPTIONS_CONTROLLED = "fairness_exceptions_controlled"
    FAIRNESS_POLICY_DEPLOYED = "fairness_policy_deployed"
    # Scanning integration rules
    COMPLIANCE_SCORE_THRESHOLD = "compliance_score_threshold"
    REQUIRED_ANALYZERS_COMPLETED = "required_analyzers_completed"
    GUARDRAIL_COVERAGE = "guardrail_coverage"
    SECURITY_REVIEW_CLEAR = "security_review_clear"
    # AIUC-1 baseline control rules (legacy — prefer framework_control_required)
    AIUC1_CONTROL_REQUIRED = "aiuc1_control_required"
    # Unified framework control rule (AIUC-1, OWASP LLM/Web, MITRE ATLAS, SLSA, NIST RMF/SSDF)
    FRAMEWORK_CONTROL_REQUIRED = "framework_control_required"


class GateEvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    NOT_EVALUATED = "not_evaluated"


class GateRuleResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"
    EXCEPTION = "exception"


class PromotionRequestStatus(StrEnum):
    PENDING_EVALUATION = "pending_evaluation"
    EVALUATION_FAILED = "evaluation_failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


# --- Fairness Enums ---


class FairnessCriticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateMode(StrEnum):
    WARN = "warn"
    BLOCK = "block"


class RiskTier(StrEnum):
    R0 = "r0"
    R1 = "r1"
    R2 = "r2"
    R3 = "r3"
    R4 = "r4"


class EvidenceType(StrEnum):
    CI_EVAL_REPORT = "ci_eval_report"
    RUNTIME_SAMPLE = "runtime_sample"
    BIAS_BENCHMARK = "bias_benchmark"
    RED_TEAM_REPORT = "red_team_report"
    GUARDRAIL_TEST = "guardrail_test"
    FAIRNESS_AUDIT = "fairness_audit"
    MODEL_CARD = "model_card"
    MANUAL_REVIEW = "manual_review"


class AttestationStatus(StrEnum):
    UNSIGNED = "unsigned"
    PENDING = "pending"
    SIGNED = "signed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"
    ACCEPTED = "accepted"
    SUPPRESSED = "suppressed"


# --- Scan Target Enums ---


class ScanFrequency(StrEnum):
    ON_PUSH = "on_push"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    ON_DEMAND = "on_demand"


class ScanTargetStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


# --- Integration Enums ---


class IntegrationType(StrEnum):
    SOURCE = "source"
    SINK = "sink"
    BIDIRECTIONAL = "bidirectional"


class IntegrationCategory(StrEnum):
    SAST = "sast"
    DAST = "dast"
    SCA = "sca"
    CONTAINER_SCAN = "container_scan"
    CLOUD_POSTURE = "cloud_posture"
    SECRETS_SCAN = "secrets_scan"
    SIEM = "siem"
    TICKETING = "ticketing"
    NOTIFICATION = "notification"
    CI_CD = "ci_cd"
    GIT_PLATFORM = "git_platform"
    VULNERABILITY_FEED = "vulnerability_feed"
    POLICY_ENGINE = "policy_engine"


class AdapterStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    PENDING_AUTH = "pending_auth"
