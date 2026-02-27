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
