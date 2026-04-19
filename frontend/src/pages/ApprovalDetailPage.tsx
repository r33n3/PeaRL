import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useApprovalThread } from "@/api/dashboard";
import { useDecideApproval, useAddComment } from "@/api/approvals";
import { useGovernanceState } from "@/api/projects";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { formatTimestamp } from "@/lib/utils";
import { CheckCircle, XCircle, HelpCircle, Send } from "lucide-react";
import type { ApprovalStatus } from "@/lib/types";

const CONTEST_TYPE_LABELS: Record<string, string> = {
  false_positive: "False Positive",
  risk_acceptance: "Risk Acceptance",
  needs_more_time: "Needs More Time",
};

function ExceptionContextPanel({
  requestData,
  projectId,
}: {
  requestData: Record<string, unknown>;
  projectId: string;
}) {
  const findingIds = (requestData.finding_ids as string[] | undefined) ?? [];
  const compensatingControls = (requestData.compensating_controls as string[] | undefined) ?? [];
  return (
    <VaultCard className="mb-6 border-clinical-cyan/20">
      <h2 className="vault-heading text-xs mb-3 text-clinical-cyan">Exception Request</h2>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <div>
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Contested Rule</p>
          <MonoText className="text-xs text-dried-blood-bright">
            {((requestData.rule_type as string) ?? "—").replace(/_/g, " ")}
          </MonoText>
        </div>
        <div>
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Contest Type</p>
          <span className="text-xs font-mono text-bone">
            {CONTEST_TYPE_LABELS[requestData.contest_type as string] ?? ((requestData.contest_type as string) ?? "—")}
          </span>
        </div>
        <div>
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Evaluation</p>
          <MonoText className="text-xs">{(requestData.evaluation_id as string) ?? "—"}</MonoText>
        </div>
        {findingIds.length > 0 && (
          <div>
            <p className="text-[10px] font-heading uppercase text-bone-dim mb-0.5">Finding IDs</p>
            <div className="flex flex-wrap gap-1">
              {findingIds.map((fid) => (
                <Link
                  key={fid}
                  to={`/projects/${projectId}/findings?highlight=${fid}`}
                  className="text-[10px] font-mono text-clinical-cyan hover:underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  {fid}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
      {!!requestData.rationale && (
        <div>
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-1">Developer Rationale</p>
          <p className="text-xs font-mono text-bone-muted leading-relaxed bg-vault-black/40 rounded px-3 py-2">
            {requestData.rationale as string}
          </p>
        </div>
      )}
      {compensatingControls.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] font-heading uppercase text-bone-dim mb-1">Compensating Controls</p>
          <ul className="space-y-0.5">
            {compensatingControls.map((c, i) => (
              <li key={i} className="text-xs font-mono text-bone-muted">{"\u2022"} {c}</li>
            ))}
          </ul>
        </div>
      )}
    </VaultCard>
  );
}

const currentUser = { id: "dashboard-user", role: "security_lead" };

export function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const { data: thread, isLoading } = useApprovalThread(approvalId!);
  const decideApproval = useDecideApproval();
  const addComment = useAddComment();

  const projectId = thread?.approval?.project_id;
  const { data: govState } = useGovernanceState(projectId);

  const [comment, setComment] = useState("");
  const [confirmReject, setConfirmReject] = useState(false);

  if (isLoading || !thread) {
    return <p className="text-bone-muted font-mono text-sm">Loading clearance record...</p>;
  }

  const { approval, comments } = thread;
  const isPending = approval.status === "pending" || approval.status === "needs_info";

  const handleApprove = () => {
    decideApproval.mutate({
      approvalId: approvalId!,
      decision: "approve",
      decidedBy: currentUser.id,
      deciderRole: currentUser.role,
      reason: "Approved via dashboard",
    });
  };

  const handleReject = () => {
    if (!confirmReject) {
      setConfirmReject(true);
      return;
    }
    decideApproval.mutate({
      approvalId: approvalId!,
      decision: "reject",
      decidedBy: currentUser.id,
      deciderRole: currentUser.role,
      reason: comment || "Rejected via dashboard",
    });
    setConfirmReject(false);
  };

  const handleRequestInfo = () => {
    if (!comment.trim()) return;
    addComment.mutate({
      approvalId: approvalId!,
      author: currentUser.id,
      authorRole: currentUser.role,
      content: comment,
      commentType: "question",
      setNeedsInfo: true,
    });
    setComment("");
  };

  const handleSendComment = () => {
    if (!comment.trim()) return;
    addComment.mutate({
      approvalId: approvalId!,
      author: currentUser.id,
      authorRole: currentUser.role,
      content: comment,
      commentType: "note",
    });
    setComment("");
  };

  return (
    <div className="max-w-4xl">
      {/* Project governance context — reviewer situational awareness */}
      {govState && (
        <VaultCard className="mb-4 border-cold-teal/20">
          <div className="flex items-start justify-between mb-3">
            <div>
              <Link
                to={`/projects/${govState.project_id}`}
                className="font-heading font-semibold text-bone hover:text-cold-teal transition-colors"
              >
                {govState.name}
              </Link>
              <MonoText className="text-xs mt-0.5">{govState.project_id}</MonoText>
            </div>
            <div className="flex items-center gap-2">
              {govState.current_environment && <EnvBadge env={govState.current_environment} />}
              {govState.risk_classification && (
                <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                  govState.risk_classification === "high" ? "bg-red-900/40 text-red-400" :
                  govState.risk_classification === "medium" ? "bg-yellow-900/40 text-yellow-400" :
                  "bg-green-900/40 text-green-400"
                }`}>
                  {govState.risk_classification} risk
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 text-xs font-mono">
            {govState.intake_card_id && (
              <div>
                <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">Intake Card</p>
                <MonoText>{govState.intake_card_id}</MonoText>
              </div>
            )}
            {govState.goal_id && (
              <div>
                <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">WTK Goal</p>
                <MonoText>{govState.goal_id}</MonoText>
              </div>
            )}
            {govState.target_id && (
              <div>
                <p className="text-bone-dim/60 text-[10px] uppercase tracking-wider mb-0.5">Target</p>
                <MonoText>{govState.target_type ? `${govState.target_type}:` : ""}{govState.target_id}</MonoText>
              </div>
            )}
          </div>

          {govState.agent_members && (
            <div className="mt-3 pt-3 border-t border-slate-border flex flex-wrap gap-2">
              {govState.agent_members.coordinator && (
                <span className="px-2 py-0.5 rounded border border-cold-teal/30 text-[10px] font-mono text-cold-teal">
                  coord: {govState.agent_members.coordinator}
                </span>
              )}
              {(govState.agent_members.workers ?? []).map((w) => (
                <span key={w} className="px-2 py-0.5 rounded border border-slate-border text-[10px] font-mono text-bone-muted">
                  worker: {w}
                </span>
              ))}
              {(govState.agent_members.evaluators ?? []).map((e) => (
                <span key={e} className="px-2 py-0.5 rounded border border-clinical-cyan/30 text-[10px] font-mono text-clinical-cyan">
                  eval: {e}
                </span>
              ))}
            </div>
          )}

          {(govState.pending_approvals_count ?? 0) > 1 && (
            <p className="mt-2 text-[10px] font-mono text-bone-dim">
              {govState.pending_approvals_count - 1} other pending approval{govState.pending_approvals_count > 2 ? "s" : ""} on this project
            </p>
          )}
        </VaultCard>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">
            {approval.request_type.replace(/_/g, " ")}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <MonoText className="text-xs">{approval.approval_request_id}</MonoText>
            <MonoText className="text-xs text-clinical-cyan">{approval.project_id}</MonoText>
            <span className="text-xs text-bone-dim">{approval.environment}</span>
          </div>
        </div>
        <StatusBadge status={approval.status as ApprovalStatus} />
      </div>

      {/* Exception context panel */}
      {approval.request_type === "exception" && approval.request_data && (
        <ExceptionContextPanel requestData={approval.request_data as Record<string, unknown>} projectId={approval.project_id} />
      )}

      {/* Evidence / request data (non-exception types) */}
      {approval.request_type !== "exception" && approval.request_data && (
        <VaultCard className="mb-6">
          <h2 className="vault-heading text-xs mb-3">Evidence Record</h2>
          <pre className="font-mono text-xs text-bone-muted whitespace-pre-wrap overflow-x-auto max-h-60">
            {JSON.stringify(approval.request_data, null, 2)}
          </pre>
        </VaultCard>
      )}

      {/* Conversation thread */}
      <h2 className="vault-heading text-sm mb-3">Conversation Thread</h2>
      <div className="space-y-3 mb-6">
        {comments.length === 0 ? (
          <p className="text-sm text-bone-dim font-mono px-4 py-4">No comments yet</p>
        ) : (
          comments.map((c) => (
            <div
              key={c.comment_id}
              className={`rounded-lg p-4 ${
                c.author_role === "agent"
                  ? "bg-charcoal border border-slate-border ml-0 mr-12"
                  : "bg-wet-stone border border-slate-border ml-12 mr-0"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-heading font-semibold text-bone uppercase">
                    {c.author}
                  </span>
                  <span className="text-[10px] font-mono text-bone-dim">
                    {c.author_role}
                  </span>
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                    c.comment_type === "question" ? "bg-clinical-cyan/10 text-clinical-cyan" :
                    c.comment_type === "evidence" ? "bg-cold-teal/10 text-cold-teal" :
                    "bg-wet-stone text-bone-muted"
                  }`}>
                    {c.comment_type}
                  </span>
                </div>
                <MonoText className="text-[10px]">{formatTimestamp(c.created_at)}</MonoText>
              </div>
              <p className="text-sm text-bone leading-relaxed">{c.content}</p>
            </div>
          ))
        )}
      </div>

      {/* Action bar */}
      {isPending && (
        <div className="border-t border-slate-border pt-4">
          <div className="flex gap-2 mb-4">
            <input
              className="input-vault flex-1"
              placeholder="Add a comment or question..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendComment()}
            />
            <button className="btn-ghost" onClick={handleSendComment} disabled={!comment.trim()}>
              <Send size={14} />
            </button>
          </div>

          <div className="flex gap-2">
            <button className="btn-teal" onClick={handleApprove}>
              <CheckCircle size={14} /> Approve
            </button>
            <button className="btn-cyan" onClick={handleRequestInfo} disabled={!comment.trim()}>
              <HelpCircle size={14} /> Request Info
            </button>
            <button
              className={`${confirmReject ? "btn-danger ring-2 ring-dried-blood-bright/50" : "btn-danger"}`}
              onClick={handleReject}
            >
              <XCircle size={14} /> {confirmReject ? "Confirm Reject" : "Reject"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
