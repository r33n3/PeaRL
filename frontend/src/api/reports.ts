import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface ReportSummary {
  report_id: string;
  report_type: string;
  status: string;
  format: string;
  generated_at: string | null;
}

export interface ReportDetail extends ReportSummary {
  content: Record<string, unknown> | null;
}

export function useReportHistory(projectId: string) {
  return useQuery({
    queryKey: ["reports", projectId],
    queryFn: () =>
      apiFetch<ReportSummary[]>(`/projects/${projectId}/reports`),
    enabled: !!projectId,
  });
}

export function useReport(projectId: string, reportId: string) {
  return useQuery({
    queryKey: ["reports", projectId, reportId],
    queryFn: () =>
      apiFetch<ReportDetail>(`/projects/${projectId}/reports/${reportId}`),
    enabled: !!projectId && !!reportId,
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      reportType,
      format = "json",
      filters,
    }: {
      projectId: string;
      reportType: string;
      format?: string;
      filters?: Record<string, string>;
    }) =>
      apiFetch<ReportDetail>(`/projects/${projectId}/reports/generate`, {
        method: "POST",
        body: JSON.stringify({
          schema_version: "1.1",
          report_type: reportType,
          format,
          filters,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
