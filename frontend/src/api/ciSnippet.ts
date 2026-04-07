import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface CiSnippetResponse {
  project_id: string;
  platform: "github_actions" | "azure_devops";
  snippet: string;
  instructions: string[];
}

export function useCiSnippet(projectId: string | undefined) {
  return useQuery({
    queryKey: ["ci-snippet", projectId],
    queryFn: () =>
      apiFetch<CiSnippetResponse>(`/projects/${projectId}/ci-snippet`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000, // snippet rarely changes — cache 5 min
  });
}
