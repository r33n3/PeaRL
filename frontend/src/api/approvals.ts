import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ApprovalRequest } from "@/lib/types";

export function useDecideApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      approvalId,
      decision,
      decidedBy,
      deciderRole,
      reason,
    }: {
      approvalId: string;
      decision: "approve" | "reject";
      decidedBy: string;
      deciderRole: string;
      reason?: string;
    }) =>
      apiFetch(`/approvals/${approvalId}/decide`, {
        method: "POST",
        body: JSON.stringify({
          schema_version: "1.1",
          approval_request_id: approvalId,
          decision,
          decided_by: decidedBy,
          decider_role: deciderRole,
          reason,
          decided_at: new Date().toISOString(),
          trace_id: `dashboard_${Date.now()}`,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      approvalId,
      author,
      authorRole,
      content,
      commentType,
      setNeedsInfo,
    }: {
      approvalId: string;
      author: string;
      authorRole: string;
      content: string;
      commentType: string;
      setNeedsInfo?: boolean;
    }) =>
      apiFetch(`/approvals/${approvalId}/comments`, {
        method: "POST",
        body: JSON.stringify({
          author,
          author_role: authorRole,
          content,
          comment_type: commentType,
          set_needs_info: setNeedsInfo ?? false,
        }),
      }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({
        queryKey: ["dashboard", "approval", variables.approvalId],
      });
    },
  });
}

export function usePendingApprovals(projectId?: string) {
  const params = projectId ? `?project_id=${projectId}` : "";
  return useQuery({
    queryKey: ["approvals", "pending", projectId],
    queryFn: () => apiFetch<ApprovalRequest[]>(`/approvals/pending${params}`),
  });
}

export function usePendingApprovalsByType(requestType?: string, projectId?: string) {
  const query = usePendingApprovals(projectId);
  return {
    ...query,
    data: requestType
      ? (query.data ?? []).filter((a) => a.request_type === requestType)
      : query.data,
  };
}
