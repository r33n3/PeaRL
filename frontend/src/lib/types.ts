// Environment chain
export type Environment = "sandbox" | "dev" | "preprod" | "prod";

// Severity levels
export type Severity = "critical" | "high" | "moderate" | "low" | "info";

// Approval
export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | "needs_info";
export type ApprovalRequestType =
  | "deployment_gate"
  | "auth_flow_change"
  | "network_policy_change"
  | "exception"
  | "remediation_execution"
  | "promotion_gate";

export interface ApprovalRequest {
  approval_request_id: string;
  project_id: string;
  environment: Environment;
  request_type: ApprovalRequestType;
  status: ApprovalStatus;
  request_data?: Record<string, unknown>;
  created_at: string | null;
  expires_at: string | null;
}

export type ExceptionStatus = "pending" | "active" | "expired" | "revoked" | "rejected";

export interface PendingException {
  exception_id: string;
  project_id: string;
  status: ExceptionStatus;
  requested_by: string;
  rationale: string;
  compensating_controls?: string[];
  scope?: Record<string, unknown>;
  approved_by?: string[];
  start_at: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export interface ApprovalComment {
  comment_id: string;
  approval_request_id: string;
  author: string;
  author_role: string;
  content: string;
  comment_type: "question" | "evidence" | "note" | "decision_note";
  attachments: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ApprovalThread {
  approval: ApprovalRequest;
  comments: ApprovalComment[];
}

// Gate evaluation
export type GateEvaluationStatus = "passed" | "failed" | "partial" | "not_evaluated";
export type GateRuleResult = "pass" | "fail" | "skip" | "warn" | "exception";

export interface RuleResult {
  rule_id: string;
  rule_type: string;
  result: GateRuleResult;
  message: string;
  details?: Record<string, unknown>;
  exception_id?: string;
}

// Findings
export type FindingStatus =
  | "open"
  | "resolved"
  | "false_positive"
  | "accepted"
  | "suppressed"
  | "closed"
  | "pending_resolution";

export interface FindingResolution {
  resolution_id: string;
  finding_id: string;
  resolved_by: string;
  approval_mode: "human" | "rescan";
  approval_status: "pending" | "approved" | "rejected" | "auto_approved";
  evidence_notes: string | null;
  commit_sha: string | null;
  pr_url: string | null;
  test_run_id: string | null;
  diff_summary: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  created_at: string | null;
}

export interface Finding {
  finding_id: string;
  project_id: string;
  title: string;
  severity: Severity;
  status: FindingStatus;
  category: string;
  environment?: string;
  source_tool: string;
  description?: string;
  cwe_ids?: string[];
  cve_id?: string;
  affected_files?: string[];
  fix_available?: boolean;
  compliance_refs?: Record<string, string[]>;
  confidence?: string;
  detected_at: string | null;
  created_at: string | null;
}

// Dashboard aggregation types
export interface ProjectSummary {
  project_id: string;
  name: string;
  environment?: string;
  pending_approvals: number;
  findings_by_severity: Record<string, number>;
  total_open_findings: number;
  gate_status: GateEvaluationStatus | null;
  gate_progress_pct: number;
  bu_id?: string | null;
}

export interface ProjectOverview extends ProjectSummary {
  gate_passed: number;
  gate_total: number;
  total_cost_usd: number;
  cost_window_start: string | null;
  cost_window_end: string | null;
  pending_approvals_list: ApprovalRequest[];
  recent_activity: ActivityEntry[];
  promotion_history: PromotionHistoryEntry[];
}

export interface ActivityEntry {
  event_type: string;
  action: string;
  actor: string;
  created_at: string | null;
}

export interface PromotionHistoryEntry {
  history_id: string;
  source_environment: Environment;
  target_environment: Environment;
  promoted_by: string;
  promoted_at: string | null;
}

// Notifications
export interface Notification {
  notification_id: string;
  project_id: string | null;
  event_type: string;
  title: string;
  body: string;
  severity: "info" | "warning" | "critical";
  read: boolean;
  link: string | null;
  created_at: string | null;
}

// Integration
export interface IntegrationEndpoint {
  endpoint_id: string;
  project_id?: string;
  name: string;
  adapter_type: string;
  integration_type: "source" | "sink" | "bidirectional";
  category: string;
  base_url: string;
  auth_config?: Record<string, unknown> | null;
  enabled: boolean;
  labels?: Record<string, string> | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
}

// Business Units
export interface BusinessUnit {
  bu_id: string;
  name: string;
  org_id: string;
  description?: string;
  framework_selections: string[];
  additional_guardrails: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

// Environment Config
export interface EnvironmentStage {
  name: string;
  order: number;
  risk_level: string;
  requires_approval: boolean;
  approval_type: string;
  use_case_ref_required: boolean;
}

export interface OrgEnvironmentConfig {
  config_id: string | null;
  org_id: string;
  stages: EnvironmentStage[];
  created_at?: string | null;
  updated_at?: string | null;
}

// Agent Brief
export interface AgentRequirement {
  control_id: string;
  rule_type?: string;
  status: "satisfied" | "missing" | "skipped";
  action?: string | null;
  evidence_ref?: string | null;
}

export interface AgentTaskPacket {
  task_packet_id: string;
  rule_id?: string | null;
  rule_type?: string | null;
  fix_guidance?: string | null;
  status: string;
  transition?: string | null;
  finding_ids?: string[];
  claimed_at?: string | null;
  agent_id?: string | null;
}

export interface AgentBrief {
  project_id: string;
  current_stage: string;
  next_stage: string | null;
  gate_status: string;
  ready_to_elevate: boolean;
  requirements: AgentRequirement[];
  resolved_requirements: ResolvedRequirement[];
  open_task_packets: AgentTaskPacket[];
  blockers_count: number;
  last_evaluated_at: string | null;
}

export interface ResolvedRequirement {
  control_id: string;
  framework: string;
  requirement_level: "mandatory" | "recommended";
  evidence_type: string;
  source: string;
  transition: string;
}

// Timeline
export interface TimelineEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  summary: string;
  detail: Record<string, unknown>;
  actor: string;
  finding_id?: string | null;
  task_packet_id?: string | null;
  evaluation_id?: string | null;
}

// Portfolio metrics (pipeline dashboard)
export interface DriftPoint {
  date: string;
  new: number;
  resolved: number;
  net: number;
}

export interface PortfolioMetrics {
  drift_series: DriftPoint[];
  mttr_days: number | null;
  mttr_trend: "improving" | "worsening" | "stable";
  mtte_days: number | null;
  velocity_new_7d: number;
  velocity_resolved_7d: number;
  blocked_projects: number;
  open_findings_total: number;
  open_critical: number;
  open_high: number;
  total_pearl_cost_usd: number;
}

export interface DomainSummary {
  enabled: number;
  total: number;
}

export interface BaselineException {
  exception_id: string;
  status: "active" | "pending";
  rationale: string;
  scope: Record<string, unknown> | null;
  expires_at: string | null;
}

export interface ProjectBaselineStatus {
  project_id: string;
  name: string;
  baseline_configured: boolean;
  baseline_id: string | null;
  org_name: string | null;
  domain_summary: Record<string, DomainSummary>;
  active_exceptions: number;
  pending_exceptions: number;
  exceptions: BaselineException[];
  inherits_org_baseline: boolean;
  scope_exclusions: string[];
  mandatory_controls: string[];
  bu_id: string | null;
  bu_name: string | null;
  baseline_source: "project" | "bu" | "org";
}

export interface OrgBaseline {
  kind: "PearlOrgBaseline";
  baseline_id: string;
  project_id: string | null;
  org_id: string | null;
  org_name: string;
  defaults: Record<string, unknown>;
  environment_defaults: Record<string, unknown> | null;
  schema_version: string;
}

export interface EnvironmentDwell {
  environment: string;
  days: number;
  entry_at: string;
  exit_at: string | null;
}

export interface ProjectGovernanceMetrics {
  mttr_days: number | null;
  findings_resolved_total: number;
  findings_open_total: number;
  resolution_rate_pct: number | null;
  gate_attempts_total: number;
  gate_pass_attempts: number;
  gate_fail_attempts: number;
  last_gate_status: string | null;
  gate_first_pass_attempt: number | null;
  days_in_pipeline: number | null;
  days_in_current_env: number | null;
  time_per_environment: EnvironmentDwell[];
  gate_decision_latency_days: number | null;
  total_cost_usd: number;
  cost_window_start: string | null;
  cost_window_end: string | null;
  exceptions_approved: number;
  exceptions_rejected: number;
  exceptions_pending: number;
  avg_time_to_approve_days: number | null;
  avg_time_to_reject_days: number | null;
}

// Promotion gate
export interface GateRuleDefinition {
  rule_id: string;
  rule_type: string;
  description: string;
  required: boolean;
  ai_only?: boolean;
  threshold?: number | null;
  parameters?: Record<string, unknown>;
}

export interface PromotionGate {
  gate_id: string;
  source_environment: Environment;
  target_environment: Environment;
  approval_mode: "auto" | "manual";
  rules: GateRuleDefinition[];
  rule_count: number;
}
