import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import {
  useFindings,
  useUpdateFindingStatus,
  useBulkUpdateFindingStatus,
  useResolveFinding,
  useGetResolution,
  useApproveResolution,
  useRejectResolution,
} from "@/api/findings";
import { useProjectOverview } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import {
  Filter,
  Bug,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  RotateCcw,
  Wrench,
  FileCode2,
  AlertTriangle,
  ArrowRight,
  CheckSquare,
  Square,
  Lock,
  AlertCircle,
  Loader2,
  Clock,
  ThumbsUp,
  ThumbsDown,
  GitCommit,
  ExternalLink,
} from "lucide-react";
import type { Severity, FindingStatus, Finding, FindingResolution } from "@/lib/types";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SEVERITIES: Severity[] = ["critical", "high", "moderate", "low", "info"];
const PAGE_SIZES = [20, 50, 100];

const STATUSES: { value: FindingStatus | "all"; label: string }[] = [
  { value: "all", label: "All Statuses" },
  { value: "open", label: "Open" },
  { value: "pending_resolution", label: "Pending Resolution" },
  { value: "resolved", label: "Resolved" },
  { value: "false_positive", label: "False Positive" },
  { value: "accepted", label: "Accepted" },
  { value: "suppressed", label: "Suppressed" },
];

const FINDING_STATUS_COLORS: Record<string, string> = {
  open: "bg-dried-blood/20 text-dried-blood-bright border border-dried-blood/40",
  pending_resolution: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  resolved: "bg-cold-teal/20 text-cold-teal border border-cold-teal/30",
  false_positive: "bg-bone-dim/20 text-bone-muted border border-bone-dim/40",
  accepted: "bg-clinical-cyan/10 text-clinical-cyan border border-clinical-cyan/20",
  suppressed: "bg-wet-stone text-bone-dim border border-slate-border",
  closed: "bg-wet-stone text-bone-dim border border-slate-border",
};

const SEVERITY_CARD_ACCENT: Record<Severity, string> = {
  critical: "border-l-dried-blood-bright",
  high: "border-l-orange-400",
  moderate: "border-l-bone-dim",
  low: "border-l-cold-teal",
  info: "border-l-clinical-cyan",
};

/** Map severity/category to which gate transitions it blocks */
function getGateBlockers(finding: Finding): string[] {
  if (finding.status !== "open" && finding.status !== "pending_resolution") return [];
  const blockers: string[] = [];
  const title = (finding.title || "").toLowerCase();

  if (finding.severity === "critical") {
    blockers.push("dev→preprod", "preprod→prod");
  } else if (finding.severity === "high") {
    blockers.push("preprod→prod");
  }
  if (title.includes("prompt injection") || title.includes("prompt_injection")) {
    if (!blockers.includes("dev→preprod")) blockers.push("dev→preprod");
  }
  if (title.includes("pii") || title.includes("data leakage")) {
    if (!blockers.includes("dev→preprod")) blockers.push("dev→preprod");
  }
  if (title.includes("guardrail")) {
    if (!blockers.includes("dev→preprod")) blockers.push("dev→preprod");
  }
  return blockers;
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function FindingStatusBadge({ status }: { status: string }) {
  const label =
    status === "pending_resolution" ? "Pending Approval" : status.replace(/_/g, " ");
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-medium ${FINDING_STATUS_COLORS[status] ?? FINDING_STATUS_COLORS.open}`}
    >
      {status === "pending_resolution" && <Clock size={10} />}
      {label}
    </span>
  );
}

function ComplianceTag({ framework, refs }: { framework: string; refs: string[] }) {
  const labels: Record<string, string> = {
    owasp_llm_top10: "OWASP LLM",
    mitre_atlas: "MITRE ATLAS",
    nist_ai_rmf: "NIST AI RMF",
    eu_ai_act: "EU AI Act",
  };
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] font-mono text-clinical-cyan/70 uppercase tracking-wider">
        {labels[framework] || framework}:
      </span>
      {refs.map((r) => (
        <MonoText
          key={r}
          className="text-[10px] bg-clinical-cyan/5 text-clinical-cyan px-1.5 py-0.5 rounded border border-clinical-cyan/15"
        >
          {r}
        </MonoText>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Fix Evidence Block (read-only)                                     */
/* ------------------------------------------------------------------ */

function EvidenceBlock({
  resolution,
  showApprovalLine = false,
}: {
  resolution: FindingResolution;
  showApprovalLine?: boolean;
}) {
  return (
    <div className="bg-wet-stone rounded border border-slate-border p-4 space-y-3">
      <h4 className="vault-heading text-[10px] text-bone-dim flex items-center gap-1">
        <ShieldCheck size={10} /> Fix Evidence
      </h4>
      {resolution.evidence_notes && (
        <p className="text-sm text-bone-muted leading-relaxed">{resolution.evidence_notes}</p>
      )}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        {resolution.commit_sha && (
          <div className="flex items-center gap-1.5 text-bone-dim">
            <GitCommit size={11} className="text-cold-teal" />
            <span className="truncate">{resolution.commit_sha}</span>
          </div>
        )}
        {resolution.pr_url && (
          <a
            href={resolution.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-clinical-cyan hover:underline truncate"
          >
            <ExternalLink size={11} /> PR / MR
          </a>
        )}
        {resolution.test_run_id && (
          <div className="flex items-center gap-1.5 text-bone-dim">
            <span className="text-[10px] uppercase tracking-wider text-bone-dim/60">Test Run:</span>
            <span>{resolution.test_run_id}</span>
          </div>
        )}
        {resolution.diff_summary && (
          <div className="col-span-2">
            <span className="text-[10px] uppercase tracking-wider text-bone-dim/60">Diff:</span>
            <p className="text-bone-muted mt-0.5">{resolution.diff_summary}</p>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 text-[10px] font-mono text-bone-dim pt-1 border-t border-slate-border">
        <span>Submitted by {resolution.resolved_by}</span>
        <span>·</span>
        <span>{resolution.approval_mode === "rescan" ? "awaiting rescan" : "awaiting human review"}</span>
        {resolution.created_at && (
          <>
            <span>·</span>
            <span>{formatTimestamp(resolution.created_at)}</span>
          </>
        )}
      </div>
      {showApprovalLine && resolution.approval_status !== "pending" && (
        <div className="flex items-center gap-2 text-[10px] font-mono pt-1 border-t border-slate-border">
          {resolution.approval_status === "approved" && (
            <span className="text-cold-teal">
              ✓ Approved by {resolution.approved_by} on {formatTimestamp(resolution.approved_at)}
            </span>
          )}
          {resolution.approval_status === "auto_approved" && (
            <span className="text-cold-teal">
              ✓ Auto-approved by rescan on {formatTimestamp(resolution.approved_at)}
            </span>
          )}
          {resolution.approval_status === "rejected" && (
            <span className="text-dried-blood-bright">
              ✗ Rejected: {resolution.rejection_reason}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Inline Resolve Form                                                */
/* ------------------------------------------------------------------ */

function ResolveForm({
  finding,
  projectId,
  onCancel,
}: {
  finding: Finding;
  projectId: string;
  onCancel: () => void;
}) {
  const [approvalMode, setApprovalMode] = useState<"human" | "rescan">("human");
  const [evidenceNotes, setEvidenceNotes] = useState("");
  const [commitSha, setCommitSha] = useState("");
  const [prUrl, setPrUrl] = useState("");
  const [testRunId, setTestRunId] = useState("");
  const [diffSummary, setDiffSummary] = useState("");

  const resolve = useResolveFinding();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    resolve.mutate(
      {
        projectId,
        findingId: finding.finding_id,
        approval_mode: approvalMode,
        evidence_notes: evidenceNotes || undefined,
        commit_sha: commitSha || undefined,
        pr_url: prUrl || undefined,
        test_run_id: testRunId || undefined,
        diff_summary: diffSummary || undefined,
      },
      { onSuccess: onCancel }
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 mt-4 pt-4 border-t border-slate-border">
      <h4 className="vault-heading text-[10px] text-bone-dim flex items-center gap-1">
        <ShieldCheck size={10} /> Submit Fix Evidence
      </h4>

      <div>
        <label className="block text-[10px] font-mono text-bone-dim mb-1 uppercase tracking-wider">
          Evidence Notes
        </label>
        <textarea
          value={evidenceNotes}
          onChange={(e) => setEvidenceNotes(e.target.value)}
          rows={3}
          placeholder="Describe what was fixed and how..."
          className="input-vault w-full text-xs resize-none"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[10px] font-mono text-bone-dim mb-1 uppercase tracking-wider">
            Commit SHA <span className="text-bone-dim/50">(optional)</span>
          </label>
          <input
            type="text"
            value={commitSha}
            onChange={(e) => setCommitSha(e.target.value)}
            placeholder="abc123f"
            className="input-vault w-full text-xs"
          />
        </div>
        <div>
          <label className="block text-[10px] font-mono text-bone-dim mb-1 uppercase tracking-wider">
            PR / MR URL <span className="text-bone-dim/50">(optional)</span>
          </label>
          <input
            type="url"
            value={prUrl}
            onChange={(e) => setPrUrl(e.target.value)}
            placeholder="https://github.com/org/repo/pull/42"
            className="input-vault w-full text-xs"
          />
        </div>
        <div>
          <label className="block text-[10px] font-mono text-bone-dim mb-1 uppercase tracking-wider">
            Test Run ID <span className="text-bone-dim/50">(optional)</span>
          </label>
          <input
            type="text"
            value={testRunId}
            onChange={(e) => setTestRunId(e.target.value)}
            placeholder="run-12345"
            className="input-vault w-full text-xs"
          />
        </div>
        <div>
          <label className="block text-[10px] font-mono text-bone-dim mb-1 uppercase tracking-wider">
            Diff Summary <span className="text-bone-dim/50">(optional)</span>
          </label>
          <input
            type="text"
            value={diffSummary}
            onChange={(e) => setDiffSummary(e.target.value)}
            placeholder="Short description of the diff"
            className="input-vault w-full text-xs"
          />
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-mono text-bone-dim mb-2 uppercase tracking-wider">
          Approval Path
        </label>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer text-xs font-mono text-bone-muted">
            <input
              type="radio"
              name="approval_mode"
              value="human"
              checked={approvalMode === "human"}
              onChange={() => setApprovalMode("human")}
              className="accent-cold-teal"
            />
            Human Review
          </label>
          <label className="flex items-center gap-2 cursor-pointer text-xs font-mono text-bone-muted">
            <input
              type="radio"
              name="approval_mode"
              value="rescan"
              checked={approvalMode === "rescan"}
              onChange={() => setApprovalMode("rescan")}
              className="accent-cold-teal"
            />
            Wait for Rescan
          </label>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          className="btn-teal text-xs py-1 px-3"
          disabled={resolve.isPending}
        >
          {resolve.isPending ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />}
          Submit Fix Evidence
        </button>
        <button
          type="button"
          className="btn-ghost text-xs py-1 px-3"
          onClick={onCancel}
          disabled={resolve.isPending}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Reviewer Actions (approve / reject)                                */
/* ------------------------------------------------------------------ */

function ReviewerActions({
  finding,
  projectId,
}: {
  finding: Finding;
  projectId: string;
}) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const approve = useApproveResolution();
  const reject = useRejectResolution();

  if (showRejectInput) {
    return (
      <div className="space-y-2">
        <textarea
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          rows={2}
          placeholder="Reason for rejection..."
          className="input-vault w-full text-xs resize-none"
          autoFocus
        />
        <div className="flex gap-2">
          <button
            className="btn-danger text-xs py-1 px-3"
            disabled={!rejectReason.trim() || reject.isPending}
            onClick={() =>
              reject.mutate({
                projectId,
                findingId: finding.finding_id,
                decided_by: "reviewer",
                rejection_reason: rejectReason,
              })
            }
          >
            {reject.isPending ? <Loader2 size={12} className="animate-spin" /> : <ThumbsDown size={12} />}
            Confirm Reject
          </button>
          <button
            className="btn-ghost text-xs py-1 px-3"
            onClick={() => setShowRejectInput(false)}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <button
        className="btn-teal text-xs py-1 px-3"
        disabled={approve.isPending}
        onClick={() =>
          approve.mutate({
            projectId,
            findingId: finding.finding_id,
            decided_by: "reviewer",
          })
        }
      >
        {approve.isPending ? <Loader2 size={12} className="animate-spin" /> : <ThumbsUp size={12} />}
        Approve
      </button>
      <button
        className="btn-danger text-xs py-1 px-3"
        onClick={() => setShowRejectInput(true)}
      >
        <ThumbsDown size={12} /> Reject
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Blocker Banner                                                     */
/* ------------------------------------------------------------------ */

function BlockerBanner({
  severityCounts,
  projectId,
}: {
  severityCounts: Record<string, number>;
  projectId: string;
}) {
  const criticalCount = severityCounts["critical"] ?? 0;
  const highCount = severityCounts["high"] ?? 0;
  const hasBlockers = criticalCount > 0 || highCount > 0;

  if (!hasBlockers) {
    return (
      <VaultCard className="mb-6 border-l-2 border-l-cold-teal">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck size={18} className="text-cold-teal" />
            <div>
              <p className="text-sm font-heading font-semibold text-cold-teal">
                No gate blockers
              </p>
              <p className="text-xs text-bone-dim font-mono">
                No critical or high severity findings blocking promotion
              </p>
            </div>
          </div>
          <Link
            to={`/projects/${projectId}/promotions`}
            className="btn-ghost text-xs py-1 px-3 flex items-center gap-1"
          >
            Pipeline <ArrowRight size={12} />
          </Link>
        </div>
      </VaultCard>
    );
  }

  return (
    <VaultCard className="mb-6 border-l-2 border-l-dried-blood-bright">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Lock size={18} className="text-dried-blood-bright" />
          <div>
            <p className="text-sm font-heading font-semibold text-dried-blood-bright">
              {criticalCount + highCount} finding
              {criticalCount + highCount !== 1 ? "s" : ""} blocking promotion
            </p>
            <div className="flex items-center gap-3 mt-1">
              {criticalCount > 0 && (
                <span className="text-xs font-mono text-dried-blood-bright">
                  {criticalCount} critical
                </span>
              )}
              {highCount > 0 && (
                <span className="text-xs font-mono text-orange-400">
                  {highCount} high
                </span>
              )}
              <span className="text-xs text-bone-dim font-mono">
                Resolve or accept to unblock gates
              </span>
            </div>
          </div>
        </div>
        <Link
          to={`/projects/${projectId}/promotions`}
          className="btn-ghost text-xs py-1 px-3 flex items-center gap-1"
        >
          Pipeline <ArrowRight size={12} />
        </Link>
      </div>
    </VaultCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Finding Card                                                       */
/* ------------------------------------------------------------------ */

function FindingCard({
  finding,
  projectId,
  isExpanded,
  isSelected,
  onToggleExpand,
  onToggleSelect,
  onStatusChange,
  isUpdating,
}: {
  finding: Finding;
  projectId: string;
  isExpanded: boolean;
  isSelected: boolean;
  onToggleExpand: () => void;
  onToggleSelect: () => void;
  onStatusChange: (status: FindingStatus) => void;
  isUpdating: boolean;
}) {
  const [showResolveForm, setShowResolveForm] = useState(false);
  const gateBlockers = getGateBlockers(finding);

  // Fetch resolution only when expanded and relevant
  const needsResolution =
    isExpanded &&
    (finding.status === "pending_resolution" || finding.status === "resolved");
  const { data: resolution } = useGetResolution(finding.finding_id, projectId, needsResolution);

  return (
    <VaultCard
      interactive
      onClick={onToggleExpand}
      className={isExpanded ? "ring-1 ring-cold-teal/30 border-cold-teal/20" : ""}
    >
      {/* Main row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <button
              className="flex-shrink-0 text-bone-dim hover:text-cold-teal transition-colors"
              onClick={(e) => { e.stopPropagation(); onToggleSelect(); }}
            >
              {isSelected ? <CheckSquare size={14} className="text-cold-teal" /> : <Square size={14} />}
            </button>
            {isExpanded
              ? <ChevronDown size={14} className="text-cold-teal flex-shrink-0" />
              : <ChevronRight size={14} className="text-bone-dim flex-shrink-0" />}
            <SeverityBadge severity={finding.severity} />
            <span className="text-sm font-heading font-semibold text-bone truncate">
              {finding.title}
            </span>
          </div>
          <div className="flex items-center gap-3 ml-14 flex-wrap">
            {finding.source_tool && <MonoText className="text-xs">{finding.source_tool}</MonoText>}
            <span className="text-xs text-bone-dim">{finding.category}</span>
            {finding.environment && <EnvBadge env={finding.environment} />}
            <FindingStatusBadge status={finding.status} />
            {finding.cve_id && <MonoText className="text-xs text-clinical-cyan">{finding.cve_id}</MonoText>}
            {finding.cwe_ids && finding.cwe_ids.length > 0 && (
              <MonoText className="text-xs text-bone-dim">
                {finding.cwe_ids.length === 1 ? finding.cwe_ids[0] : `${finding.cwe_ids[0]} +${finding.cwe_ids.length - 1}`}
              </MonoText>
            )}
            {gateBlockers.length > 0 && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono text-dried-blood-bright bg-dried-blood/10 px-1.5 py-0.5 rounded border border-dried-blood/20">
                <Lock size={9} />
                BLOCKS: {gateBlockers.join(", ")}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <MonoText className="text-xs text-bone-dim">{formatTimestamp(finding.detected_at)}</MonoText>
          {finding.fix_available && (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono text-cold-teal">
              <Wrench size={10} /> fix available
            </span>
          )}
          {finding.confidence && (
            <span className="text-[10px] font-mono text-bone-dim">conf: {finding.confidence}</span>
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-slate-border space-y-4" onClick={(e) => e.stopPropagation()}>
          {finding.description && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim">Description</h4>
              <p className="text-sm text-bone-muted leading-relaxed">{finding.description}</p>
            </div>
          )}

          {finding.compliance_refs && Object.keys(finding.compliance_refs).length > 0 && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim flex items-center gap-1">
                <ShieldAlert size={10} /> Compliance Frameworks
              </h4>
              <div className="space-y-1.5">
                {Object.entries(finding.compliance_refs).map(([fw, refs]) => (
                  <ComplianceTag key={fw} framework={fw} refs={refs} />
                ))}
              </div>
            </div>
          )}

          {finding.cwe_ids && finding.cwe_ids.length > 0 && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim flex items-center gap-1">
                <AlertTriangle size={10} /> CWE References
              </h4>
              <div className="flex flex-wrap gap-2">
                {finding.cwe_ids.map((cwe) => (
                  <MonoText key={cwe} className="text-xs bg-wet-stone px-2 py-0.5 rounded border border-slate-border">{cwe}</MonoText>
                ))}
              </div>
            </div>
          )}

          {finding.cve_id && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim">CVE</h4>
              <MonoText className="text-xs text-clinical-cyan bg-clinical-cyan/5 px-2 py-1 rounded border border-clinical-cyan/20">{finding.cve_id}</MonoText>
            </div>
          )}

          {finding.affected_files && finding.affected_files.length > 0 && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim flex items-center gap-1">
                <FileCode2 size={10} /> Affected Files
              </h4>
              <div className="bg-wet-stone rounded border border-slate-border p-3 space-y-1 max-h-40 overflow-y-auto">
                {finding.affected_files.map((file, idx) => (
                  <MonoText key={idx} className="block text-xs text-bone-muted">{file}</MonoText>
                ))}
              </div>
            </div>
          )}

          {gateBlockers.length > 0 && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-dried-blood-bright flex items-center gap-1">
                <Lock size={10} /> Gate Impact
              </h4>
              <p className="text-xs text-bone-muted">
                This finding blocks promotion through:{" "}
                <span className="text-dried-blood-bright font-mono">{gateBlockers.join(", ")}</span>.
                Resolve or accept risk to unblock.
              </p>
            </div>
          )}

          {/* Resolution evidence block — pending or resolved */}
          {resolution && (finding.status === "pending_resolution" || finding.status === "resolved") && (
            <EvidenceBlock
              resolution={resolution}
              showApprovalLine={finding.status === "resolved"}
            />
          )}

          {/* Reviewer actions for pending_resolution */}
          {finding.status === "pending_resolution" && resolution && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim">Reviewer Actions</h4>
              <ReviewerActions finding={finding} projectId={projectId} />
            </div>
          )}

          {/* Actions */}
          {finding.status !== "pending_resolution" && finding.status !== "resolved" && (
            <div>
              <h4 className="vault-heading text-[10px] mb-2 text-bone-dim">Actions</h4>
              {showResolveForm ? (
                <ResolveForm
                  finding={finding}
                  projectId={projectId}
                  onCancel={() => setShowResolveForm(false)}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  <button
                    className="btn-teal text-xs py-1 px-3"
                    disabled={isUpdating}
                    onClick={() => setShowResolveForm(true)}
                  >
                    <ShieldCheck size={12} /> Resolve
                  </button>
                  {finding.status !== "false_positive" && (
                    <button className="btn-ghost text-xs py-1 px-3" disabled={isUpdating} onClick={() => onStatusChange("false_positive")}>
                      <ShieldX size={12} /> False Positive
                    </button>
                  )}
                  {finding.status !== "accepted" && (
                    <button className="btn-ghost text-xs py-1 px-3" disabled={isUpdating} onClick={() => onStatusChange("accepted")}>
                      <ShieldAlert size={12} /> Accept Risk
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Reopen for resolved/false_positive/accepted/suppressed */}
          {(finding.status === "resolved" || finding.status === "false_positive" || finding.status === "accepted" || finding.status === "suppressed") && (
            <div className="pt-2">
              <button className="btn-danger text-xs py-1 px-3" disabled={isUpdating} onClick={() => onStatusChange("open")}>
                <RotateCcw size={12} /> Reopen
              </button>
            </div>
          )}
        </div>
      )}
    </VaultCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Pagination                                                         */
/* ------------------------------------------------------------------ */

function Pagination({
  total,
  limit,
  offset,
  onPageChange,
  onPageSizeChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between mt-6 pt-4 border-t border-slate-border">
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-bone-dim">
          Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-bone-dim font-mono">per page:</span>
          {PAGE_SIZES.map((size) => (
            <button
              key={size}
              onClick={() => onPageSizeChange(size)}
              className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                limit === size
                  ? "bg-cold-teal/15 text-cold-teal border border-cold-teal/30"
                  : "text-bone-dim hover:text-bone border border-transparent"
              }`}
            >
              {size}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={!canPrev}
          className="p-1.5 rounded text-bone-dim hover:text-cold-teal disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-xs font-mono text-bone-muted">
          {currentPage} / {totalPages}
        </span>
        <button
          onClick={() => onPageChange(offset + limit)}
          disabled={!canNext}
          className="p-1.5 rounded text-bone-dim hover:text-cold-teal disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export function FindingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [filterSeverity, setFilterSeverity] = useState<Severity | "all">("all");
  const [filterStatus, setFilterStatus] = useState<FindingStatus | "all">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pageSize, setPageSize] = useState(20);
  const [offset, setOffset] = useState(0);

  const queryFilters = useMemo(() => {
    const f: { severity?: string; status?: string } = {};
    if (filterSeverity !== "all") f.severity = filterSeverity;
    if (filterStatus !== "all") f.status = filterStatus;
    return f;
  }, [filterSeverity, filterStatus]);

  const pagination = useMemo(() => ({ limit: pageSize, offset }), [pageSize, offset]);

  const { data, isLoading, isError, error } = useFindings(projectId!, queryFilters, pagination);
  useProjectOverview(projectId!);
  const updateStatus = useUpdateFindingStatus();
  const bulkUpdate = useBulkUpdateFindingStatus();

  const findings = data?.items ?? [];
  const total = data?.total ?? 0;
  const severityCounts = data?.severity_counts ?? {};

  function handleStatusChange(findingId: string, newStatus: FindingStatus) {
    if (!projectId) return;
    updateStatus.mutate({ projectId, findingId, status: newStatus });
  }

  function handleBulkAction(status: string) {
    if (!projectId || selectedIds.size === 0) return;
    bulkUpdate.mutate(
      { projectId, findingIds: Array.from(selectedIds), status },
      { onSuccess: () => setSelectedIds(new Set()) }
    );
  }

  function toggleSelect(findingId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(findingId)) next.delete(findingId);
      else next.add(findingId);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === findings.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(findings.map((f) => f.finding_id)));
    }
  }

  function handleFilterChange(sev: Severity | "all") {
    setFilterSeverity(sev);
    setOffset(0);
    setSelectedIds(new Set());
  }

  function handleStatusFilterChange(s: FindingStatus | "all") {
    setFilterStatus(s);
    setOffset(0);
    setSelectedIds(new Set());
  }

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setOffset(0);
    setSelectedIds(new Set());
  }

  function handlePageChange(newOffset: number) {
    setOffset(newOffset);
    setSelectedIds(new Set());
    setExpandedId(null);
  }

  // --- Error state ---
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <AlertCircle size={40} className="text-dried-blood-bright/60" />
        <p className="text-bone-muted font-mono text-sm">Failed to load findings</p>
        <MonoText className="text-xs text-bone-dim">{(error as Error)?.message ?? "Unknown error"}</MonoText>
      </div>
    );
  }

  // --- Loading state ---
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 size={32} className="text-cold-teal/50 animate-spin" />
        <p className="text-bone-muted font-mono text-sm">Scanning findings archive...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">Findings</h1>
          <MonoText className="text-xs">{projectId}</MonoText>
        </div>
        <div className="flex items-center gap-2">
          <Bug size={16} className="text-bone-muted" />
          <span className="text-xl font-heading font-bold text-bone">{total}</span>
          <span className="text-xs text-bone-muted">
            {filterSeverity === "all" && filterStatus === "all" ? "total" : "matching"}
          </span>
        </div>
      </div>

      {/* Blocker banner */}
      <BlockerBanner severityCounts={severityCounts} projectId={projectId!} />

      {/* Severity summary cards */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        {SEVERITIES.map((sev) => {
          const count = severityCounts[sev] ?? 0;
          const isActive = filterSeverity === sev;
          return (
            <VaultCard
              key={sev}
              interactive
              onClick={() => handleFilterChange(isActive ? "all" : sev)}
              className={`text-center border-l-2 ${SEVERITY_CARD_ACCENT[sev]} ${isActive ? "ring-1 ring-cold-teal/50" : ""}`}
            >
              <p className="text-2xl font-heading font-bold text-bone">{count}</p>
              <SeverityBadge severity={sev} />
            </VaultCard>
          );
        })}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-bone-muted flex-shrink-0" />
          <div className="flex gap-1 flex-wrap">
            <button
              className={`px-3 py-1 rounded-full text-xs font-mono transition-colors ${
                filterSeverity === "all"
                  ? "bg-cold-teal/15 text-cold-teal border border-cold-teal/30"
                  : "bg-wet-stone text-bone-muted border border-slate-border hover:text-bone"
              }`}
              onClick={() => handleFilterChange("all")}
            >
              all
            </button>
            {SEVERITIES.map((sev) => (
              <button
                key={sev}
                className={`px-3 py-1 rounded-full text-xs font-mono transition-colors ${
                  filterSeverity === sev
                    ? "bg-cold-teal/15 text-cold-teal border border-cold-teal/30"
                    : "bg-wet-stone text-bone-muted border border-slate-border hover:text-bone"
                }`}
                onClick={() => handleFilterChange(filterSeverity === sev ? "all" : sev)}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-bone-dim font-mono">status:</span>
          <select
            value={filterStatus}
            onChange={(e) => handleStatusFilterChange(e.target.value as FindingStatus | "all")}
            className="input-vault text-xs py-1 px-2 w-auto min-w-[160px] appearance-none cursor-pointer"
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-4 mb-4 px-4 py-3 bg-cold-teal/5 border border-cold-teal/20 rounded-lg">
          <button onClick={toggleSelectAll} className="text-xs font-mono text-cold-teal hover:text-bone transition-colors">
            {selectedIds.size === findings.length ? "Deselect all" : "Select all"}
          </button>
          <span className="text-xs font-mono text-bone-dim">{selectedIds.size} selected</span>
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-bone-dim font-mono">Mark as:</span>
            <button className="btn-ghost text-xs py-1 px-3" disabled={bulkUpdate.isPending} onClick={() => handleBulkAction("false_positive")}>False Positive</button>
            <button className="btn-ghost text-xs py-1 px-3" disabled={bulkUpdate.isPending} onClick={() => handleBulkAction("accepted")}>Accept Risk</button>
            <button className="btn-ghost text-xs py-1 px-3" disabled={bulkUpdate.isPending} onClick={() => handleBulkAction("suppressed")}>Suppress</button>
          </div>
        </div>
      )}

      {/* Select all hint */}
      {findings.length > 0 && selectedIds.size === 0 && (
        <div className="flex items-center gap-2 mb-4">
          <button onClick={toggleSelectAll} className="flex items-center gap-1.5 text-xs font-mono text-bone-dim hover:text-cold-teal transition-colors">
            <Square size={12} /> Select all for bulk triage
          </button>
        </div>
      )}

      {/* Empty state */}
      {findings.length === 0 ? (
        <VaultCard className="text-center py-16">
          <ShieldCheck size={40} className="text-cold-teal/40 mx-auto mb-4" />
          <p className="text-bone-dim font-mono text-sm">No findings match the current filters</p>
          <p className="text-bone-dim font-mono text-xs mt-1">
            {filterSeverity !== "all" || filterStatus !== "all"
              ? "Try broadening your filter criteria"
              : "No security findings detected for this project"}
          </p>
          {(filterSeverity !== "all" || filterStatus !== "all") && (
            <button className="btn-ghost text-xs mt-4" onClick={() => { handleFilterChange("all"); setFilterStatus("all"); }}>
              Clear Filters
            </button>
          )}
        </VaultCard>
      ) : (
        <>
          {/* Finding cards */}
          <div className="space-y-3">
            {findings.map((finding, i) => (
              <div
                key={finding.finding_id}
                className={i < 15 ? "stagger-item" : ""}
                style={i < 15 ? { animationDelay: `${i * 40}ms` } : undefined}
              >
                <FindingCard
                  finding={finding}
                  projectId={projectId!}
                  isExpanded={expandedId === finding.finding_id}
                  isSelected={selectedIds.has(finding.finding_id)}
                  onToggleExpand={() => setExpandedId((prev) => prev === finding.finding_id ? null : finding.finding_id)}
                  onToggleSelect={() => toggleSelect(finding.finding_id)}
                  onStatusChange={(status) => handleStatusChange(finding.finding_id, status)}
                  isUpdating={updateStatus.isPending}
                />
              </div>
            ))}
          </div>

          {/* Pagination */}
          {total > pageSize && (
            <Pagination
              total={total}
              limit={pageSize}
              offset={offset}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          )}
        </>
      )}
    </div>
  );
}
