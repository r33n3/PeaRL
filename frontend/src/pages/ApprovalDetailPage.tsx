import { useState } from "react";
import { useParams } from "react-router-dom";
import { useApprovalThread } from "@/api/dashboard";
import { useDecideApproval, useAddComment } from "@/api/approvals";
import { VaultCard } from "@/components/shared/VaultCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import { CheckCircle, XCircle, HelpCircle, Send } from "lucide-react";
import type { ApprovalStatus } from "@/lib/types";

export function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const { data: thread, isLoading } = useApprovalThread(approvalId!);
  const decideApproval = useDecideApproval();
  const addComment = useAddComment();

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
      decidedBy: "dashboard-user",
      deciderRole: "security_lead",
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
      decidedBy: "dashboard-user",
      deciderRole: "security_lead",
      reason: comment || "Rejected via dashboard",
    });
    setConfirmReject(false);
  };

  const handleRequestInfo = () => {
    if (!comment.trim()) return;
    addComment.mutate({
      approvalId: approvalId!,
      author: "dashboard-user",
      authorRole: "security_lead",
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
      author: "dashboard-user",
      authorRole: "security_lead",
      content: comment,
      commentType: "note",
    });
    setComment("");
  };

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">
            {approval.request_type.replace(/_/g, " ")}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <MonoText className="text-xs">{approval.approval_request_id}</MonoText>
            <span className="text-xs text-bone-dim">{approval.environment}</span>
          </div>
        </div>
        <StatusBadge status={approval.status as ApprovalStatus} />
      </div>

      {/* Evidence / request data */}
      {approval.request_data && (
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
