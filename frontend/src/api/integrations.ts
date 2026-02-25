import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { IntegrationEndpoint } from "@/lib/types";

export function useIntegrations(projectId: string) {
  return useQuery({
    queryKey: ["integrations", projectId],
    queryFn: () =>
      apiFetch<IntegrationEndpoint[]>(`/projects/${projectId}/integrations`),
    enabled: !!projectId,
  });
}

export function useCreateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      data,
    }: {
      projectId: string;
      data: {
        name: string;
        adapter_type: string;
        integration_type: string;
        category: string;
        base_url: string;
        labels?: Record<string, string>;
      };
    }) =>
      apiFetch(`/projects/${projectId}/integrations`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

export function useUpdateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      endpointId,
      data,
    }: {
      projectId: string;
      endpointId: string;
      data: Record<string, unknown>;
    }) =>
      apiFetch(`/projects/${projectId}/integrations/${endpointId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

export function useDeleteIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      endpointId,
    }: {
      projectId: string;
      endpointId: string;
    }) =>
      apiFetch(`/projects/${projectId}/integrations/${endpointId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

export function useTestIntegration() {
  return useMutation({
    mutationFn: ({
      projectId,
      endpointId,
    }: {
      projectId: string;
      endpointId: string;
    }) =>
      apiFetch<{ success: boolean; message?: string }>(
        `/projects/${projectId}/integrations/${endpointId}/test`,
        { method: "POST" }
      ),
  });
}
