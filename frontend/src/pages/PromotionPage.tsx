import { useState } from "react";
import { useParams } from "react-router-dom";
import { usePromotionReadiness, usePromotionHistory, useRequestPromotion, useContestRule } from "@/api/promotions";
import { usePendingApprovals } from "@/api/approvals";
import { useProjectOverview } from "@/api/dashboard";
import { VaultCard } from "@/components/shared/VaultCard";
import { EnvBadge } from "@/components/shared/EnvBadge";
import { GateProgress } from "@/components/shared/GateProgress";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import { ArrowRight, CheckCircle, XCircle, MinusCircle, AlertTriangle, ArrowUpCircle, Clock, X } from "lucide-react";
import type { Environment, GateRuleResult } from "@/lib/types";

const ENV_ORDER: Environment[] = ["sandbox", "dev", "preprod", "prod"];

const RULE_ICONS: Record<GateRuleResult, { icon: typeof CheckCircle; color: string }> = {
  pass: { icon: CheckCircle, color: "text-cold-teal" },
  fail: { icon: XCircle, color: "text-dried-blood-bright" },
  skip: { icon: MinusCircle, color: "text-bone-dim" },
  warn: { icon: AlertTriangle, color: "text-clinical-cyan" },
  exception: { icon: AlertTriangle, color: "text-bone-muted" },
};

const CONTEST_TYPE_LABELS: Record<string, string> = {
  false_positive: "False Positive",
  risk_acceptance: "Risk Acceptance",
  needs_more_time: "Needs More Time",
};

export function PromotionPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { data: overview } = useProjectOverview(projectId!);
  const { data: readiness, isLoading: readinessLoading } = usePromotionReadiness(projectId!);
  const { data: history } = usePromotionHistory(projectId!);
  const requestPromotion = useRequestPromotion();
  const contestRule = useContestRule();
  const { data: pendingApprovals } = usePendingApprovals(projectId);

  const [contestingRule, setContestingRule] = useState<string | null>(null);
  const [contestType, setContestType] = useState<"false_positive" | "risk_acceptance" | "needs_more_time">("false_positive");
  const [rationale, setRationale] = useState("");

  const overviewData = overview as Record<string, any> | undefined;
  const currentEnv = overviewData?.environment ?? "dev";
  const readinessData = readiness as Record<string, any> | undefined;
  const ruleResults = (readinessData?.rule_results ?? []) as Array<{
    rule_id: string;
    rule_type: string;
    result: GateRuleResult;
    message: string;
  }>;

  const passed = readinessData?.passed_count ?? 0;
  const total = readinessData?.total_count ?? 0;
  const blockers = (readinessData?.blockers ?? []) as string[];
  const isReady = readinessData?.status === "passed";
  const evaluationId = readinessData?.evaluation_id as string | undefined;

  // Check if a rule already has a pending exception approval
  function pendingForRule(ruleType: string): boolean {
    return (pendingApprovals ?? []).some(
      (a) =>
        a.request_type === "exception" &&
        (a.request_data as any)?.rule_type === ruleType
    );
  }

  function handleCloseModal() {
    setContestingRule(null);
    setRationale("");
    setContestType("false_positive");
  }

  function handleSubmitContest() {
    if (!contestingRule || !rationale.trim() || !evaluationId) return;
    contestRule.mutate(
      {
        projectId: projectId!,
        body: {
          evaluation_id: evaluationId,
          rule_type: contestingRule,
          contest_type: contestType,
          rationale: rationale.trim(),
        },
      },
      {
        onSuccess: () => {
          handleCloseModal();
        },
      }
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">Promotion Pipeline</h1>
          <MonoText className="text-xs">{projectId}</MonoText>
        </div>
      </div>

      {/* Pipeline visualization */}
      <VaultCard className="mb-6">
        <div className="flex items-center justify-center gap-1 py-4">
          {ENV_ORDER.map((env, i) => (
            <div key={env} className="flex items-center gap-1">
              <div
                className={`flex flex-col items-center gap-1 px-4 py-2 rounded-lg border transition-all ${
                  env === currentEnv
                    ? "bg-cold-teal/15 border-cold-teal text-cold-teal shadow-teal-glow"
                    : ENV_ORDER.indexOf(env) < ENV_ORDER.indexOf(currentEnv as Environment)
                      ? "bg-wet-stone border-bone-dim text-bone-muted"
                      : "border-slate-border border-dashed text-bone-dim"
                }`}
              >
                <span className="text-xs font-heading font-bold uppercase">{env}</span>
              </div>
              {i < ENV_ORDER.length - 1 && (
                <ArrowRight size={14} className={
                  ENV_ORDER.indexOf(env) < ENV_ORDER.indexOf(currentEnv as Environment)
                    ? "text-bone-dim"
                    : "text-slate-border"
                } />
              )}
            </div>
          ))}
        </div>
      </VaultCard>

      {/* Gate readiness */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <VaultCard className="col-span-2">
          <h2 className="vault-heading text-xs mb-4">Gate Rules</h2>
          {readinessLoading ? (
            <p className="text-bone-muted font-mono text-sm">Evaluating gates...</p>
          ) : ruleResults.length === 0 ? (
            <p className="text-bone-dim font-mono text-sm">No gate evaluation available. Run a scan first.</p>
          ) : (
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {ruleResults.map((rule) => {
                const { icon: Icon, color } = RULE_ICONS[rule.result] ?? RULE_ICONS.skip;
                const isPending = pendingForRule(rule.rule_type);
                return (
                  <div key={rule.rule_id} className="flex items-center gap-3 px-3 py-2 rounded bg-vault-black/50">
                    <Icon size={14} className={color} />
                    <span className="text-xs font-mono text-bone-muted flex-1">
                      {rule.rule_type.replace(/_/g, " ")}
                    </span>
                    <span className={`text-[10px] font-mono ${color}`}>{rule.result}</span>
                    {rule.result === "fail" && !isPending && evaluationId && (
                      <button
                        className="text-[10px] font-mono text-clinical-cyan hover:underline ml-1"
                        onClick={() => setContestingRule(rule.rule_type)}
                      >
                        Contest
                      </button>
                    )}
                    {rule.result === "fail" && isPending && (
                      <span className="text-[10px] font-mono text-bone-muted/60 flex items-center gap-1 ml-1">
                        <Clock size={10} /> Under review
                      </span>
                    )}
                    {rule.result === "exception" && (
                      <span className="text-[10px] font-mono text-bone-muted/60 ml-1">exception active</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </VaultCard>

        <div className="space-y-4">
          <VaultCard>
            <h2 className="vault-heading text-xs mb-2">Progress</h2>
            <GateProgress passed={passed} total={total} />
            <p className="text-xs font-mono text-bone-muted mt-2">
              {readinessData?.status ?? "not evaluated"}
            </p>
          </VaultCard>

          {blockers.length > 0 && (
            <VaultCard className="border-dried-blood/30">
              <h2 className="vault-heading text-xs mb-2 text-dried-blood-bright">Blockers</h2>
              <ul className="space-y-1">
                {blockers.map((b, i) => (
                  <li key={i} className="text-xs text-bone-muted font-mono">{"\u2022"} {b}</li>
                ))}
              </ul>
            </VaultCard>
          )}

          <div className="space-y-2">
            <button
              className="btn-cyan w-full"
              onClick={() => requestPromotion.mutate(projectId!)}
              disabled={!isReady || requestPromotion.isPending}
            >
              <ArrowUpCircle size={14} />
              {requestPromotion.isPending ? "Requesting..." : "Request Promotion"}
            </button>
          </div>
        </div>
      </div>

      {/* Promotion history */}
      <h2 className="vault-heading text-sm mb-3">History</h2>
      <VaultCard>
        {!(history as any[])?.length ? (
          <p className="text-bone-dim font-mono text-sm py-4 text-center">No promotion history</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-xs font-heading uppercase tracking-wider text-bone-muted border-b border-slate-border">
                <th className="text-left py-2 px-3">From</th>
                <th className="text-left py-2 px-3">To</th>
                <th className="text-left py-2 px-3">Promoted By</th>
                <th className="text-left py-2 px-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {(history as any[])?.map((h: any) => (
                <tr key={h.history_id} className="border-b border-slate-border/50 hover:bg-wet-stone/50">
                  <td className="py-2 px-3"><EnvBadge env={h.source_environment} /></td>
                  <td className="py-2 px-3"><EnvBadge env={h.target_environment} /></td>
                  <td className="py-2 px-3 font-mono text-xs text-bone-muted">{h.promoted_by}</td>
                  <td className="py-2 px-3"><MonoText className="text-xs">{formatTimestamp(h.promoted_at)}</MonoText></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </VaultCard>

      {/* Contest modal */}
      {contestingRule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-vault-black/80 backdrop-blur-sm">
          <div className="bg-charcoal border border-slate-border rounded-lg w-full max-w-md mx-4 shadow-lg">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-border">
              <div>
                <h2 className="vault-heading text-sm">Contest Rule</h2>
                <MonoText className="text-xs text-bone-dim">{contestingRule.replace(/_/g, " ")}</MonoText>
              </div>
              <button className="text-bone-dim hover:text-bone" onClick={handleCloseModal}>
                <X size={16} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              {/* Contest type */}
              <div>
                <label className="vault-heading text-xs block mb-2">Contest Type</label>
                <div className="space-y-2">
                  {(["false_positive", "risk_acceptance", "needs_more_time"] as const).map((ct) => (
                    <label key={ct} className="flex items-start gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="contestType"
                        value={ct}
                        checked={contestType === ct}
                        onChange={() => setContestType(ct)}
                        className="mt-0.5 accent-clinical-cyan"
                      />
                      <div>
                        <span className="text-xs font-mono text-bone">{CONTEST_TYPE_LABELS[ct]}</span>
                        <p className="text-[10px] font-mono text-bone-dim">
                          {ct === "false_positive" && "Not a real finding — triggered incorrectly"}
                          {ct === "risk_acceptance" && "Accept the risk with compensating controls"}
                          {ct === "needs_more_time" && "Temporary exception — fix in progress"}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Rationale */}
              <div>
                <label className="vault-heading text-xs block mb-2">Rationale <span className="text-dried-blood-bright">*</span></label>
                <textarea
                  className="input-vault w-full h-24 resize-none"
                  placeholder="Explain why this rule result should be contested..."
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                />
              </div>

              <p className="text-[10px] font-mono text-bone-dim">
                You can add evidence links as comments after submitting.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-slate-border">
              <button className="btn-ghost text-xs" onClick={handleCloseModal}>
                Cancel
              </button>
              <button
                className="btn-cyan text-xs"
                onClick={handleSubmitContest}
                disabled={!rationale.trim() || contestRule.isPending}
              >
                {contestRule.isPending ? "Submitting..." : "Submit for Review"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
