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
