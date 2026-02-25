import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

// Keyed by environment stage key (e.g. "sandbox", "dev", or any custom key)
export type EnvironmentRequirements = Record<string, string[]>;

export interface OrgBaselineData {
  baseline_id: string;
  project_id: string;
  org_name: string;
  defaults: Record<string, Record<string, unknown>>;
  environment_defaults: Record<string, unknown> | null;
  environment_requirements: EnvironmentRequirements | null;
  schema_version: string;
}

export function useOrgBaseline(projectId: string) {
  return useQuery({
    queryKey: ["org-baseline", projectId],
    queryFn: () =>
      apiFetch<OrgBaselineData>(`/projects/${projectId}/org-baseline`),
    enabled: !!projectId,
    retry: false,
  });
}

export function useSaveOrgBaseline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      data,
    }: {
      projectId: string;
      data: Record<string, unknown>;
    }) =>
      apiFetch(`/projects/${projectId}/org-baseline`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-baseline"] });
    },
  });
}
