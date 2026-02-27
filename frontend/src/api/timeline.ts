import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { TimelineEvent } from "@/lib/types";

export function useProjectTimeline(projectId?: string, limit = 50) {
  return useQuery({
    queryKey: ["timeline", projectId],
    queryFn: () =>
      apiFetch<TimelineEvent[]>(`/projects/${projectId}/timeline?limit=${limit}`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });
}
