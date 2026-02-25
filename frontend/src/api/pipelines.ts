import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface PipelineStage {
  key: string;
  label: string;
  description?: string;
  order: number;
}

export interface PipelineData {
  pipeline_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  stages: PipelineStage[];
  is_default: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export function usePipelines() {
  return useQuery({
    queryKey: ["pipelines"],
    queryFn: () => apiFetch<PipelineData[]>("/pipelines"),
  });
}

export function useDefaultPipeline() {
  return useQuery({
    queryKey: ["pipelines", "default"],
    queryFn: () => apiFetch<PipelineData>("/pipelines/default"),
  });
}

export function useCreatePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<PipelineData>) =>
      apiFetch<PipelineData>("/pipelines", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}

export function useUpdatePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      pipelineId,
      data,
    }: {
      pipelineId: string;
      data: Partial<PipelineData>;
    }) =>
      apiFetch<PipelineData>(`/pipelines/${pipelineId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}

export function useDeletePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pipelineId }: { pipelineId: string }) =>
      apiFetch(`/pipelines/${pipelineId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}

export function useSetDefaultPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pipelineId }: { pipelineId: string }) =>
      apiFetch(`/pipelines/${pipelineId}/set-default`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}
