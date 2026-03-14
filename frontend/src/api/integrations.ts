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

// --- Org-level hooks (project_id = NULL) ---

export function useOrgIntegrations() {
  return useQuery({
    queryKey: ["org-integrations"],
    queryFn: () => apiFetch<IntegrationEndpoint[]>("/integrations"),
  });
}

export function useCreateOrgIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      adapter_type: string;
      integration_type: string;
      category: string;
      base_url: string;
      auth_config?: Record<string, unknown>;
      labels?: Record<string, string>;
    }) =>
      apiFetch<IntegrationEndpoint>("/integrations", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-integrations"] });
    },
  });
}

export function useUpdateOrgIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      endpointId,
      data,
    }: {
      endpointId: string;
      data: Record<string, unknown>;
    }) =>
      apiFetch<IntegrationEndpoint>(`/integrations/${endpointId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-integrations"] });
    },
  });
}

export function useDeleteOrgIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ endpointId }: { endpointId: string }) =>
      apiFetch(`/integrations/${endpointId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-integrations"] });
    },
  });
}

export function useTestOrgIntegration() {
  return useMutation({
    mutationFn: ({ endpointId }: { endpointId: string }) =>
      apiFetch<{ success: boolean; message?: string }>(
        `/integrations/${endpointId}/test`,
        { method: "POST" }
      ),
  });
}

export function useEventRouting() {
  return useQuery({
    queryKey: ["event-routing"],
    queryFn: () =>
      apiFetch<{ routing: Record<string, string[]> }>("/integrations/event-routing"),
  });
}

export function useSaveEventRouting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { routing: Record<string, string[]> }) =>
      apiFetch<{ routing: Record<string, string[]> }>("/integrations/event-routing", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["event-routing"] });
    },
  });
}
