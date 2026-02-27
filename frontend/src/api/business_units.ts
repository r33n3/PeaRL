import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { BusinessUnit } from "@/lib/types";

export function useBusinessUnits(orgId?: string) {
  return useQuery({
    queryKey: ["business-units", orgId],
    queryFn: () =>
      apiFetch<BusinessUnit[]>(`/business-units${orgId ? `?org_id=${orgId}` : ""}`),
  });
}

export function useCreateBU() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      org_id: string;
      name: string;
      description?: string;
      framework_selections?: string[];
      additional_guardrails?: Record<string, unknown>;
    }) =>
      apiFetch<BusinessUnit>("/business-units", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["business-units"] }),
  });
}

export function useUpdateBU() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      buId,
      ...body
    }: {
      buId: string;
      name?: string;
      description?: string;
      additional_guardrails?: Record<string, unknown>;
    }) =>
      apiFetch<BusinessUnit>(`/business-units/${buId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["business-units"] }),
  });
}

export function useDeleteBU() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (buId: string) =>
      apiFetch(`/business-units/${buId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["business-units"] }),
  });
}

export function useSetBUFrameworks() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      buId,
      framework_selections,
    }: {
      buId: string;
      framework_selections: string[];
    }) =>
      apiFetch<{ bu_id: string; frameworks: string[]; requirements_created: number }>(
        `/business-units/${buId}/frameworks`,
        {
          method: "POST",
          body: JSON.stringify({ framework_selections }),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["business-units"] }),
  });
}

export function useBURequirements(buId?: string) {
  return useQuery({
    queryKey: ["bu-requirements", buId],
    queryFn: () => apiFetch<Record<string, unknown>[]>(`/business-units/${buId}/requirements`),
    enabled: !!buId,
  });
}
