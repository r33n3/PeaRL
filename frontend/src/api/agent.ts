import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { AgentBrief } from "@/lib/types";

export function useAgentBrief(projectId?: string) {
  return useQuery({
    queryKey: ["agent-brief", projectId],
    queryFn: () =>
      apiFetch<AgentBrief>(`/projects/${projectId}/promotions/agent-brief`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });
}

export interface PackageIntegrity {
  package_id: string | null;
  compiled_at: string | null;
  status: "current" | "stale" | "tampered" | "missing";
  hash_valid: boolean | null;
  source_drift: boolean | null;
  drift_details: string[];
  days_since_compiled: number | null;
}

export function usePackageIntegrity(projectId?: string) {
  return useQuery({
    queryKey: ["package-integrity", projectId],
    queryFn: () =>
      apiFetch<PackageIntegrity>(`/projects/${projectId}/compiled-package/integrity`),
    enabled: !!projectId,
    refetchInterval: 60_000,
  });
}
