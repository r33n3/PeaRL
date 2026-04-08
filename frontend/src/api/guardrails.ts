import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface BedrockConfig {
  name: string;
  description: string;
  topicPolicyConfig?: object;
  contentPolicyConfig?: object;
  sensitiveInformationPolicyConfig?: object;
  note?: string;
}

export interface CedarPolicy {
  policy_id: string;
  type: string;
  statement: string;
  description: string;
}

export interface GuardrailRecommendation {
  id: string;
  name: string;
  description: string;
  category: string;
  severity: string;
  implementation_steps: string[];
  code_examples?: Record<string, string>;
  bedrock_config?: BedrockConfig;
  cedar_policy?: CedarPolicy;
  source?: string;        // "pearl" | "mass" | "snyk" | "sonarqube"
  policy_type?: string;   // "cedar" | "bedrock" | "litellm" | "nginx" | "nemo"
  content?: Record<string, unknown> | string;  // raw policy content from scanner
}

export interface GuardrailsResponse {
  project_id: string;
  project_type: string;
  target_platforms: string[];
  open_findings_count: number;
  recommended_guardrails: GuardrailRecommendation[];
}

export function useRecommendedGuardrails(projectId: string | undefined) {
  return useQuery<GuardrailsResponse>({
    queryKey: ["guardrails", "recommended", projectId],
    queryFn: () =>
      apiFetch<GuardrailsResponse>(`/projects/${projectId}/recommended-guardrails`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGuardrails(category?: string) {
  const path = category ? `/guardrails?category=${category}` : `/guardrails`;
  return useQuery<GuardrailRecommendation[]>({
    queryKey: ["guardrails", "list", category],
    queryFn: () => apiFetch<GuardrailRecommendation[]>(path),
    staleTime: 5 * 60 * 1000,
  });
}
