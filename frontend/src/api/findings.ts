import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Finding } from "@/lib/types";

export interface FindingsPage {
  items: Finding[];
  total: number;
  limit: number;
  offset: number;
  severity_counts: Record<string, number>;
}

export function useFindings(
  projectId: string,
  filters?: { severity?: string; status?: string; category?: string },
  pagination?: { limit: number; offset: number }
) {
  const params = new URLSearchParams();
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.category) params.set("category", filters.category);
  if (pagination) {
    params.set("limit", String(pagination.limit));
    params.set("offset", String(pagination.offset));
  }
  const qs = params.toString();

  return useQuery({
    queryKey: ["findings", projectId, filters, pagination],
    queryFn: () =>
      apiFetch<FindingsPage>(
        `/projects/${projectId}/findings${qs ? `?${qs}` : ""}`
      ),
    enabled: !!projectId,
  });
}

export function useUpdateFindingStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      findingId,
      status,
    }: {
      projectId: string;
      findingId: string;
      status: string;
    }) =>
      apiFetch(`/projects/${projectId}/findings/${findingId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useBulkUpdateFindingStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      findingIds,
      status,
    }: {
      projectId: string;
      findingIds: string[];
      status: string;
    }) =>
      apiFetch<{ updated_count: number; status: string }>(
        `/projects/${projectId}/findings/bulk-status`,
        {
          method: "POST",
          body: JSON.stringify({ finding_ids: findingIds, status }),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
