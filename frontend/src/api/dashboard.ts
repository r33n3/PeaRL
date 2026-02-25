import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ProjectSummary,
  ApprovalRequest,
  ApprovalThread,
  Notification,
} from "@/lib/types";

export function useProjects() {
  return useQuery({
    queryKey: ["dashboard", "projects"],
    queryFn: () => apiFetch<ProjectSummary[]>("/dashboard/projects"),
    refetchInterval: 30000,
  });
}

export function useProjectOverview(projectId: string) {
  return useQuery({
    queryKey: ["dashboard", "project", projectId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/dashboard/projects/${projectId}/overview`),
    enabled: !!projectId,
  });
}

export function usePendingApprovals(projectId?: string) {
  const params = projectId ? `?project_id=${projectId}` : "";
  return useQuery({
    queryKey: ["dashboard", "approvals", "pending", projectId],
    queryFn: () => apiFetch<ApprovalRequest[]>(`/dashboard/approvals/pending${params}`),
    refetchInterval: 15000,
  });
}

export function useApprovalThread(approvalId: string) {
  return useQuery({
    queryKey: ["dashboard", "approval", approvalId, "thread"],
    queryFn: () => apiFetch<ApprovalThread>(`/dashboard/approvals/${approvalId}/thread`),
    enabled: !!approvalId,
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: ["dashboard", "notifications"],
    queryFn: () => apiFetch<Notification[]>("/dashboard/notifications"),
    refetchInterval: 10000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      apiFetch(`/dashboard/notifications/${notificationId}/read`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard", "notifications"] });
    },
  });
}
