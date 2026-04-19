import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface AgentMembers {
  coordinator: string | null;
  workers: string[];
  evaluators: string[];
}

export interface PendingApprovalSummary {
  approval_request_id: string;
  request_type: string;
  status: string;
  environment: string;
  created_at: string | null;
}

export interface GovernanceState {
  project_id: string;
  name: string;
  current_environment: string | null;
  intake_card_id: string | null;
  goal_id: string | null;
  target_type: string | null;
  target_id: string | null;
  risk_classification: string | null;
  agent_members: AgentMembers | null;
  litellm_key_refs: string[] | null;
  memory_policy_refs: string[] | null;
  qualification_packet_id: string | null;
  pending_approvals: PendingApprovalSummary[];
  pending_approvals_count: number;
  gate_status: {
    package_id: string;
    compiled_at: string | null;
    environment: string | null;
  } | null;
}

export interface RegisterAgentsPayload {
  coordinator?: string;
  workers?: string[];
  evaluators?: string[];
  litellm_key_refs?: string[];
  memory_policy_refs?: string[];
  goal_id?: string;
  intake_card_id?: string;
  target_type?: string;
  target_id?: string;
  risk_classification?: string;
  qualification_packet_id?: string;
}

export function useGovernanceState(projectId: string | undefined) {
  return useQuery({
    queryKey: ["governance-state", projectId],
    queryFn: () => apiFetch<GovernanceState>(`/projects/${projectId}/governance-state`),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

export function useRegisterAgents(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisterAgentsPayload) =>
      apiFetch<GovernanceState>(`/projects/${projectId}/agents`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["governance-state", projectId] });
    },
  });
}
