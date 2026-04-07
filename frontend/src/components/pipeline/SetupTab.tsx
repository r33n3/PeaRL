import { useState } from "react";
import { Copy, Check, Terminal, AlertCircle } from "lucide-react";
import { useCiSnippet } from "@/api/ciSnippet";
import { VaultCard } from "@/components/shared/VaultCard";

interface SetupTabProps {
  projectId: string | undefined;
}

export function SetupTab({ projectId }: SetupTabProps) {
  const { data, isLoading, isError } = useCiSnippet(projectId);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!data?.snippet) return;
    await navigator.clipboard.writeText(data.snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-12 justify-center">
        <Terminal size={14} className="animate-pulse" /> Generating workflow...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 text-dried-blood-bright text-sm font-mono py-12 justify-center">
        <AlertCircle size={14} /> Failed to load CI snippet
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-sm font-mono text-bone-bright uppercase tracking-widest mb-1">
          CI/CD Setup
        </h2>
        <p className="text-xs font-mono text-bone-muted">
          Add this workflow to your repository to connect PeaRL governance gates to your CI pipeline.
        </p>
      </div>

      {/* Checklist */}
      <VaultCard>
        <div className="flex items-center gap-2 mb-3">
          <Check size={14} className="text-bone-muted" />
          <span className="text-xs font-mono text-bone-muted uppercase tracking-widest">
            Setup Checklist
          </span>
        </div>
        <ol className="space-y-2">
          {data.instructions.map((instruction, i) => (
            <li key={i} className="flex items-start gap-3 text-xs font-mono text-bone-dim">
              <span className="shrink-0 w-5 h-5 rounded border border-white/20 flex items-center justify-center text-xs text-bone-muted">
                {i + 1}
              </span>
              <span className="leading-relaxed">{instruction}</span>
            </li>
          ))}
        </ol>
      </VaultCard>

      {/* Snippet */}
      <VaultCard>
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <Terminal size={14} className="text-bone-muted" />
            <span className="text-xs font-mono text-bone-muted uppercase tracking-widest">
              {data.platform === "github_actions" ? "GitHub Actions Workflow" : "Azure Pipelines"}
            </span>
          </div>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs font-mono px-3 py-1 rounded border border-white/20 text-bone-muted hover:text-bone-bright hover:border-white/40 transition-colors"
          >
            {copied ? (
              <><Check size={11} className="text-cold-teal" /> Copied</>
            ) : (
              <><Copy size={11} /> Copy</>
            )}
          </button>
        </div>
        <div className="text-xs font-mono text-bone-dim mb-2">
          Save as{" "}
          <code className="text-cold-teal bg-white/5 px-1 rounded">
            {data.platform === "github_actions"
              ? ".github/workflows/pearl-gate.yml"
              : "azure-pipelines.yml"}
          </code>
        </div>
        <pre className="text-xs font-mono text-green-300/80 bg-black/30 rounded p-4 overflow-x-auto whitespace-pre leading-relaxed border border-white/5">
          {data.snippet}
        </pre>
      </VaultCard>
    </div>
  );
}
