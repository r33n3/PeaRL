import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

export function usePromotionReadiness(projectId: string) {
  return useQuery({
    queryKey: ["promotions", "readiness", projectId],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(`/projects/${projectId}/promotions/readiness`),
    enabled: !!projectId,
  });
}

export function usePromotionHistory(projectId: string) {
  return useQuery({
    queryKey: ["promotions", "history", projectId],
    queryFn: () =>
      apiFetch<Record<string, unknown>[]>(`/projects/${projectId}/promotions/history`),
    enabled: !!projectId,
  });
}

export function useRequestPromotion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      apiFetch(`/projects/${projectId}/promotions/request`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["promotions"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface GateData {
  gate_id: string;
  source_environment: string;
  target_environment: string;
  approval_mode: "auto" | "manual";
  rules: GateRuleData[];
  rule_count: number;
}

export interface GateRuleData {
  rule_id: string;
  rule_type: string;
  description: string;
  required: boolean;
  ai_only?: boolean;
  threshold?: number | null;
  parameters?: Record<string, unknown>;
}

export function useGates() {
  return useQuery({
    queryKey: ["promotions", "gates"],
    queryFn: () => apiFetch<GateData[]>("/promotions/gates"),
  });
}

export function useUpdateGateRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gateId,
      rules,
    }: {
      gateId: string;
      rules: GateRuleData[];
    }) =>
      apiFetch("/promotions/gates", {
        method: "POST",
        body: JSON.stringify({ gate_id: gateId, rules }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["promotions", "gates"] });
    },
  });
}

export function useCreateGate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceEnvironment,
      targetEnvironment,
      rules,
    }: {
      sourceEnvironment: string;
      targetEnvironment: string;
      rules?: GateRuleData[];
    }) =>
      apiFetch("/promotions/gates", {
        method: "POST",
        body: JSON.stringify({
          source_environment: sourceEnvironment,
          target_environment: targetEnvironment,
          rules: rules ?? [],
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["promotions", "gates"] });
    },
  });
}

export function useDeleteGate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ gateId }: { gateId: string }) =>
      apiFetch(`/promotions/gates/${gateId}`, { method: "DELETE" }),
    // Optimistically remove the gate immediately so the UI updates without
    // waiting for the server round-trip or query invalidation.
    onMutate: async ({ gateId }) => {
      await qc.cancelQueries({ queryKey: ["promotions", "gates"] });
      const previous = qc.getQueryData<GateData[]>(["promotions", "gates"]);
      qc.setQueryData<GateData[]>(["promotions", "gates"], (old) =>
        old ? old.filter((g) => g.gate_id !== gateId) : old
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      // Roll back the optimistic removal if the server rejected the delete.
      if (context?.previous) {
        qc.setQueryData(["promotions", "gates"], context.previous);
      }
    },
    onSettled: () => {
      // Always sync with the server state after success or error.
      qc.invalidateQueries({ queryKey: ["promotions", "gates"] });
    },
  });
}

/** Static catalogue of all gate rule types with metadata for the Add Rule picker. */
export const GATE_RULE_TYPES: {
  value: string;
  label: string;
  group: string;
  hasThreshold: boolean;
  aiOnly: boolean;
  hasParams: boolean;
}[] = [
  // Framework (unified multi-framework control — preferred over legacy per-control types)
  { value: "framework_control_required", label: "Framework Control Required", group: "Framework", hasThreshold: false, aiOnly: false, hasParams: true },
  // Core
  { value: "project_registered", label: "Project Registered", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "org_baseline_attached", label: "Org Baseline Attached", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "app_spec_defined", label: "App Spec Defined", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "no_hardcoded_secrets", label: "No Hardcoded Secrets", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "unit_tests_exist", label: "Unit Tests Exist", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "unit_test_coverage", label: "Unit Test Coverage", group: "Core", hasThreshold: true, aiOnly: false, hasParams: false },
  { value: "integration_test_coverage", label: "Integration Test Coverage", group: "Core", hasThreshold: true, aiOnly: false, hasParams: false },
  { value: "security_baseline_tests", label: "Security Baseline Tests", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "critical_findings_zero", label: "Zero Critical Findings", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "high_findings_zero", label: "Zero High Findings", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "data_classifications_documented", label: "Data Classifications Documented", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "iam_roles_defined", label: "IAM Roles Defined", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "network_boundaries_declared", label: "Network Boundaries Declared", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "all_controls_verified", label: "All Controls Verified", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "security_review_approval", label: "Security Review Approval", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "exec_sponsor_approval", label: "Exec Sponsor Approval", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "residual_risk_report", label: "Residual Risk Report", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "read_only_autonomy", label: "Read-Only Autonomy Mode", group: "Core", hasThreshold: false, aiOnly: false, hasParams: false },
  // Security
  { value: "scan_target_registered", label: "Scan Target Registered", group: "Security", hasThreshold: false, aiOnly: false, hasParams: false },
  { value: "security_review_clear", label: "Security Review Clear", group: "Security", hasThreshold: false, aiOnly: false, hasParams: false },
  // AI / MASS
  { value: "mass_scan_completed", label: "MASS Scan Completed", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "mass_risk_acceptable", label: "MASS Risk Acceptable", group: "AI", hasThreshold: true, aiOnly: true, hasParams: false },
  { value: "comprehensive_mass_scan", label: "Comprehensive MASS Scan", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "rai_eval_completed", label: "RAI Evaluation Completed", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "model_card_documented", label: "Model Card Documented", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "required_analyzers_completed", label: "Required Analyzers Completed", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "compliance_score_threshold", label: "Compliance Score Threshold", group: "AI", hasThreshold: true, aiOnly: true, hasParams: false },
  { value: "guardrail_coverage", label: "Guardrail Coverage", group: "AI", hasThreshold: false, aiOnly: true, hasParams: false },
  // Fairness
  { value: "fairness_case_defined", label: "Fairness Case Defined", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_requirements_met", label: "Fairness Requirements Met", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_evidence_current", label: "Fairness Evidence Current", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_attestation_signed", label: "Fairness Attestation Signed", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_hard_blocks_clear", label: "Fairness Hard Blocks Clear", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_drift_acceptable", label: "Fairness Drift Acceptable", group: "Fairness", hasThreshold: true, aiOnly: true, hasParams: false },
  { value: "fairness_context_receipt_valid", label: "Fairness Context Receipt Valid", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_exceptions_controlled", label: "Fairness Exceptions Controlled", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "fairness_policy_deployed", label: "Fairness Policy Deployed", group: "Fairness", hasThreshold: false, aiOnly: true, hasParams: false },
  // Legacy — superseded by framework_control_required; kept for backward compatibility with existing gates
  { value: "no_prompt_injection", label: "No Prompt Injection (use OWASP LLM01)", group: "Legacy", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "guardrails_verified", label: "Guardrails Verified (use AIUC-1 C003)", group: "Legacy", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "no_pii_leakage", label: "No PII Leakage (use OWASP LLM06)", group: "Legacy", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "owasp_llm_top10_clear", label: "OWASP LLM Top 10 Clear (use per-control)", group: "Legacy", hasThreshold: false, aiOnly: true, hasParams: false },
  { value: "aiuc1_control_required", label: "AIUC-1 Control Required (use Framework)", group: "Legacy", hasThreshold: false, aiOnly: false, hasParams: true },
];

export interface ContestRuleBody {
  evaluation_id: string;
  rule_type: string;
  contest_type: "false_positive" | "risk_acceptance" | "needs_more_time";
  rationale: string;
  finding_ids?: string[];
  compensating_controls?: string[];
  expires_days?: number;
}

export function useContestRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, body }: { projectId: string; body: ContestRuleBody }) =>
      apiFetch(`/projects/${projectId}/promotions/contest-rule`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useUpdateGateApprovalMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gateId,
      approvalMode,
    }: {
      gateId: string;
      approvalMode: "auto" | "manual";
    }) =>
      apiFetch(`/promotions/gates/${gateId}/approval-mode`, {
        method: "POST",
        body: JSON.stringify({ approval_mode: approvalMode }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["promotions"] });
    },
  });
}
