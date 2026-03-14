import { useState } from "react";
import { Trash2, AlertTriangle } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import { MonoText } from "@/components/shared/MonoText";
import { useProjects } from "@/api/dashboard";
import { useDeleteProject, useDeleteAllProjects } from "@/api/dashboard";

export function AdminProjectsPage() {
  const { data: projects = [], isLoading } = useProjects();
  const deleteProject = useDeleteProject();
  const deleteAll = useDeleteAllProjects();

  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [confirmingAll, setConfirmingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDeleteOne(projectId: string) {
    setError(null);
    try {
      await deleteProject.mutateAsync(projectId);
      setConfirmingId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function handleDeleteAll() {
    setError(null);
    try {
      await deleteAll.mutateAsync();
      setConfirmingAll(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm font-mono text-bone-dim">
          Permanently delete projects and all dependent data.
        </p>

        {!confirmingAll ? (
          <button
            className="btn-ghost text-xs text-dried-blood-bright hover:bg-dried-blood-bright/10 flex items-center gap-1.5"
            onClick={() => setConfirmingAll(true)}
            disabled={projects.length === 0 || deleteAll.isPending}
          >
            <Trash2 size={13} />
            Wipe All Projects
          </button>
        ) : (
          <div className="flex items-center gap-2 border border-dried-blood-bright/40 rounded-md px-3 py-2 bg-dried-blood-bright/5">
            <AlertTriangle size={13} className="text-dried-blood-bright" />
            <span className="text-xs font-mono text-dried-blood-bright">
              Delete all {projects.length} project{projects.length !== 1 ? "s" : ""}?
            </span>
            <button
              className="text-xs font-heading font-semibold text-dried-blood-bright border border-dried-blood-bright/50 rounded px-2 py-0.5 hover:bg-dried-blood-bright/20 disabled:opacity-50"
              onClick={handleDeleteAll}
              disabled={deleteAll.isPending}
            >
              {deleteAll.isPending ? "Deleting…" : "Confirm"}
            </button>
            <button
              className="text-xs font-heading text-bone-muted hover:text-bone"
              onClick={() => setConfirmingAll(false)}
              disabled={deleteAll.isPending}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 rounded border border-dried-blood-bright/50 bg-dried-blood-bright/10 text-xs font-mono text-dried-blood-bright">
          Error: {error}
        </div>
      )}

      {isLoading && (
        <p className="text-sm font-mono text-bone-dim">Loading projects…</p>
      )}

      <div className="space-y-3">
        {projects.map((project) => (
          <VaultCard key={project.project_id} className="border border-slate-border/60">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-heading font-semibold text-sm text-bone">{project.name}</p>
                <MonoText className="text-[10px] text-bone-dim">{project.project_id}</MonoText>
              </div>

              <div className="flex items-center gap-2">
                {project.environment && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-wet-stone border border-slate-border text-bone-dim">
                    {project.environment}
                  </span>
                )}

                {confirmingId === project.project_id ? (
                  <div className="flex items-center gap-2 border border-dried-blood-bright/40 rounded-md px-2 py-1 bg-dried-blood-bright/5">
                    <span className="text-xs font-mono text-dried-blood-bright">Sure?</span>
                    <button
                      className="text-xs font-heading font-semibold text-dried-blood-bright border border-dried-blood-bright/50 rounded px-2 py-0.5 hover:bg-dried-blood-bright/20 disabled:opacity-50"
                      onClick={() => handleDeleteOne(project.project_id)}
                      disabled={deleteProject.isPending}
                    >
                      {deleteProject.isPending ? "…" : "Delete"}
                    </button>
                    <button
                      className="text-xs font-heading text-bone-muted hover:text-bone"
                      onClick={() => setConfirmingId(null)}
                      disabled={deleteProject.isPending}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    className="btn-ghost text-xs text-dried-blood-bright hover:bg-dried-blood-bright/10 flex items-center gap-1"
                    onClick={() => setConfirmingId(project.project_id)}
                    disabled={deleteProject.isPending || deleteAll.isPending}
                  >
                    <Trash2 size={12} />
                    Delete
                  </button>
                )}
              </div>
            </div>
          </VaultCard>
        ))}

        {!isLoading && projects.length === 0 && (
          <p className="text-sm font-mono text-bone-dim text-center py-8">
            No projects found.
          </p>
        )}
      </div>
    </div>
  );
}
