import { useState } from "react";
import { useParams } from "react-router-dom";
import { useProjectOverview } from "@/api/dashboard";
import {
  useReportHistory,
  useReport,
  useGenerateReport,
} from "@/api/reports";
import type { ReportDetail } from "@/api/reports";
import { VaultCard } from "@/components/shared/VaultCard";
import { MonoText } from "@/components/shared/MonoText";
import { formatTimestamp } from "@/lib/utils";
import {
  ShieldCheck,
  AlertTriangle,
  CheckSquare,
  TrendingUp,
  Brain,
  Globe,
  FileText,
  Clock,
  Loader2,
} from "lucide-react";

/* ── Report type definitions ── */

const REPORT_TYPES = [
  {
    id: "release_readiness",
    name: "Release Readiness",
    icon: ShieldCheck,
    description: "Gate compliance and deployment readiness assessment",
  },
  {
    id: "residual_risk",
    name: "Residual Risk",
    icon: AlertTriangle,
    description: "Outstanding risks and accepted exceptions",
  },
  {
    id: "control_coverage",
    name: "Control Coverage",
    icon: CheckSquare,
    description: "Security control implementation vs requirements",
  },
  {
    id: "findings_trend",
    name: "Findings Trend",
    icon: TrendingUp,
    description: "30-day finding trends by severity",
  },
  {
    id: "rai_posture",
    name: "RAI Posture",
    icon: Brain,
    description: "Responsible AI posture and compliance assessment",
  },
  {
    id: "environment_posture",
    name: "Environment Posture",
    icon: Globe,
    description: "Cross-environment security posture comparison",
  },
] as const;

/* ── Helpers ── */

function reportStatusBadge(status: string) {
  const map: Record<string, string> = {
    completed: "badge-approved",
    generating: "badge-pending",
    failed: "badge-critical",
    pending: "badge-pending",
  };
  return map[status] ?? "badge-info";
}

function formatReportType(type: string): string {
  const entry = REPORT_TYPES.find((r) => r.id === type);
  if (entry) return entry.name;
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/* ── Release readiness renderer ── */

function ReleaseReadinessContent({ content }: { content: Record<string, unknown> }) {
  const ready = content.ready ?? content.is_ready ?? content.release_ready;
  const blockers = (content.blockers ?? content.blocking_items ?? []) as Array<string | Record<string, unknown>>;
  const riskFactors = (content.risk_factors ?? content.risks ?? []) as Array<string | Record<string, unknown>>;
  const findingsBySeverity = (content.findings_by_severity ?? content.findings ?? {}) as Record<string, number>;
  const promotion = content.promotion_readiness ?? content.promotion ?? null;

  return (
    <div className="space-y-5">
      {/* Ready badge */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-heading uppercase tracking-wider text-bone-muted">
          Ready
        </span>
        {ready ? (
          <span className="badge-approved">Yes</span>
        ) : (
          <span className="badge-critical">No</span>
        )}
      </div>

      {/* Blockers */}
      {blockers.length > 0 && (
        <div>
          <h4 className="text-xs font-heading uppercase tracking-wider text-dried-blood-bright mb-2">
            Blockers
          </h4>
          <ul className="space-y-1">
            {blockers.map((b, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-dried-blood-bright font-mono bg-dried-blood/10 border border-dried-blood/20 rounded px-3 py-2"
              >
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                <span>{typeof b === "string" ? b : JSON.stringify(b)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Risk factors */}
      {riskFactors.length > 0 && (
        <div>
          <h4 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-2">
            Risk Factors
          </h4>
          <ul className="space-y-1">
            {riskFactors.map((r, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-bone-muted font-mono bg-wet-stone/50 border border-slate-border rounded px-3 py-2"
              >
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-clinical-cyan" />
                <span>{typeof r === "string" ? r : JSON.stringify(r)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Findings by severity */}
      {Object.keys(findingsBySeverity).length > 0 && (
        <div>
          <h4 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-2">
            Findings by Severity
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
            {Object.entries(findingsBySeverity).map(([severity, count]) => {
              const colorMap: Record<string, string> = {
                critical: "text-dried-blood-bright",
                high: "text-orange-400",
                moderate: "text-bone-muted",
                low: "text-cold-teal",
                info: "text-clinical-cyan",
              };
              return (
                <div
                  key={severity}
                  className="bg-wet-stone/50 border border-slate-border rounded px-3 py-2 text-center"
                >
                  <p className={`text-lg font-heading font-bold ${colorMap[severity] ?? "text-bone"}`}>
                    {count}
                  </p>
                  <MonoText className="text-[10px]">{severity}</MonoText>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Promotion readiness */}
      {promotion !== null && promotion !== undefined && (
        <div>
          <h4 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-2">
            Promotion Readiness
          </h4>
          {typeof promotion === "object" && promotion !== null ? (
            <div className="bg-wet-stone/50 border border-slate-border rounded px-4 py-3 space-y-2">
              {Object.entries(promotion as Record<string, unknown>).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between">
                  <MonoText className="text-xs">{key.replace(/_/g, " ")}</MonoText>
                  <span className="text-sm text-bone font-mono">
                    {typeof value === "boolean" ? (
                      value ? (
                        <span className="text-cold-teal">pass</span>
                      ) : (
                        <span className="text-dried-blood-bright">fail</span>
                      )
                    ) : (
                      String(value)
                    )}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-bone font-mono">{String(promotion)}</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Generic JSON content renderer ── */

function GenericReportContent({ content }: { content: Record<string, unknown> }) {
  return (
    <div className="space-y-4">
      {Object.entries(content).map(([key, value]) => (
        <div key={key}>
          <h4 className="text-xs font-heading uppercase tracking-wider text-bone-muted mb-1">
            {key.replace(/_/g, " ")}
          </h4>
          {value !== null && typeof value === "object" && !Array.isArray(value) ? (
            <div className="bg-wet-stone/50 border border-slate-border rounded px-4 py-3 space-y-1.5">
              {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <MonoText className="text-xs">{k.replace(/_/g, " ")}</MonoText>
                  <span className="text-sm text-bone font-mono">{String(v)}</span>
                </div>
              ))}
            </div>
          ) : Array.isArray(value) ? (
            <ul className="space-y-1">
              {value.map((item, i) => (
                <li
                  key={i}
                  className="text-sm text-bone font-mono bg-wet-stone/50 border border-slate-border rounded px-3 py-2"
                >
                  {typeof item === "object" && item !== null
                    ? JSON.stringify(item)
                    : String(item)}
                </li>
              ))}
              {value.length === 0 && (
                <li className="text-sm text-bone-dim font-mono italic">None</li>
              )}
            </ul>
          ) : (
            <p className="text-sm text-bone font-mono">
              {value === null || value === undefined ? "---" : String(value)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Report detail viewer ── */

function ReportViewer({
  projectId,
  reportId,
  reportType,
  inlineReport,
}: {
  projectId: string;
  reportId: string;
  reportType: string;
  inlineReport?: ReportDetail | null;
}) {
  const { data: fetched, isLoading } = useReport(projectId, reportId);
  const report = inlineReport ?? fetched;

  if (isLoading && !inlineReport) {
    return (
      <VaultCard>
        <div className="flex items-center justify-center gap-2 py-8">
          <Loader2 size={16} className="animate-spin text-cold-teal" />
          <span className="text-bone-muted font-mono text-sm">Loading report...</span>
        </div>
      </VaultCard>
    );
  }

  if (!report) return null;

  const content = report.content;

  return (
    <VaultCard className="mt-4">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-border">
        <div className="flex items-center gap-3">
          <FileText size={16} className="text-cold-teal" />
          <div>
            <h3 className="text-sm font-heading font-semibold text-bone">
              {formatReportType(report.report_type)}
            </h3>
            <MonoText className="text-[10px]">{report.report_id}</MonoText>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={reportStatusBadge(report.status)}>{report.status}</span>
          <MonoText className="text-[10px]">{formatTimestamp(report.generated_at)}</MonoText>
        </div>
      </div>

      {!content ? (
        <p className="text-bone-dim font-mono text-sm text-center py-6">
          No content available for this report.
        </p>
      ) : reportType === "release_readiness" ? (
        <ReleaseReadinessContent content={content} />
      ) : (
        <GenericReportContent content={content} />
      )}
    </VaultCard>
  );
}

/* ── Main page ── */

export function ReportsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { data: overviewData, isLoading: overviewLoading } = useProjectOverview(projectId!);
  const { data: history, isLoading: historyLoading } = useReportHistory(projectId!);
  const generateMutation = useGenerateReport();

  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedReportType, setSelectedReportType] = useState<string>("");
  const [generatedReport, setGeneratedReport] = useState<ReportDetail | null>(null);
  const [generatingType, setGeneratingType] = useState<string | null>(null);

  const overview = overviewData as Record<string, unknown> | undefined;

  function handleGenerate(reportType: string) {
    if (!projectId || generatingType) return;
    setGeneratingType(reportType);
    setSelectedReportId(null);
    setGeneratedReport(null);

    generateMutation.mutate(
      { projectId, reportType },
      {
        onSuccess: (data) => {
          setGeneratedReport(data);
          setSelectedReportType(reportType);
          setGeneratingType(null);
        },
        onError: () => {
          setGeneratingType(null);
        },
      },
    );
  }

  function handleSelectHistory(reportId: string, reportType: string) {
    setGeneratedReport(null);
    setSelectedReportId(reportId);
    setSelectedReportType(reportType);
  }

  return (
    <div>
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="vault-heading text-2xl">Reports & Audit</h1>
          <MonoText className="text-xs">{projectId}</MonoText>
        </div>
      </div>

      {/* Report type cards */}
      <h2 className="vault-heading text-sm mb-3">Generate Report</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {REPORT_TYPES.map(({ id, name, icon: Icon, description }, idx) => {
          const isGenerating = generatingType === id;

          return (
            <VaultCard
              key={id}
              interactive
              onClick={() => handleGenerate(id)}
              className={`stagger-item ${isGenerating ? "ring-1 ring-cold-teal/40" : ""}`}
              style={{ animationDelay: `${idx * 60}ms` }}
            >
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-md bg-cold-teal/10 flex-shrink-0">
                  <Icon size={16} className="text-cold-teal" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-heading font-semibold text-bone">{name}</h3>
                  <p className="text-xs text-bone-muted mt-1">{description}</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-border">
                {isGenerating ? (
                  <div className="flex items-center gap-2">
                    <Loader2 size={12} className="animate-spin text-cold-teal" />
                    <MonoText className="text-[10px] text-cold-teal">Generating...</MonoText>
                  </div>
                ) : (
                  <MonoText className="text-[10px]">Click to generate</MonoText>
                )}
                <button
                  className="btn-teal text-[10px] px-2 py-0.5"
                  disabled={!!generatingType}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleGenerate(id);
                  }}
                >
                  Generate
                </button>
              </div>
            </VaultCard>
          );
        })}
      </div>

      {/* Generated / selected report viewer */}
      {generatedReport && (
        <ReportViewer
          projectId={projectId!}
          reportId={generatedReport.report_id}
          reportType={selectedReportType}
          inlineReport={generatedReport}
        />
      )}
      {selectedReportId && !generatedReport && (
        <ReportViewer
          projectId={projectId!}
          reportId={selectedReportId}
          reportType={selectedReportType}
        />
      )}

      {/* Report history */}
      <h2 className="vault-heading text-sm mb-3 mt-8 flex items-center gap-2">
        <FileText size={14} /> Report History
      </h2>
      <VaultCard>
        {historyLoading ? (
          <div className="flex items-center justify-center gap-2 py-6">
            <Loader2 size={16} className="animate-spin text-cold-teal" />
            <span className="text-bone-muted font-mono text-sm">Loading history...</span>
          </div>
        ) : !history?.length ? (
          <p className="text-bone-dim font-mono text-sm py-6 text-center">
            No reports generated yet. Select a report type above to begin.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-border">
                  <th className="text-left py-2 px-3 text-[10px] font-heading uppercase tracking-wider text-bone-muted">
                    Type
                  </th>
                  <th className="text-left py-2 px-3 text-[10px] font-heading uppercase tracking-wider text-bone-muted">
                    Format
                  </th>
                  <th className="text-left py-2 px-3 text-[10px] font-heading uppercase tracking-wider text-bone-muted">
                    Generated
                  </th>
                  <th className="text-left py-2 px-3 text-[10px] font-heading uppercase tracking-wider text-bone-muted">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-border/50">
                {history.map((row) => {
                  const isSelected = selectedReportId === row.report_id;
                  return (
                    <tr
                      key={row.report_id}
                      className={`cursor-pointer transition-colors hover:bg-wet-stone/40 ${
                        isSelected ? "bg-cold-teal/5" : ""
                      }`}
                      onClick={() => handleSelectHistory(row.report_id, row.report_type)}
                    >
                      <td className="py-2.5 px-3 text-bone font-mono text-xs">
                        {formatReportType(row.report_type)}
                      </td>
                      <td className="py-2.5 px-3">
                        <MonoText className="text-xs">{row.format}</MonoText>
                      </td>
                      <td className="py-2.5 px-3">
                        <MonoText className="text-xs">{formatTimestamp(row.generated_at)}</MonoText>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={reportStatusBadge(row.status)}>{row.status}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </VaultCard>

      {/* Cost summary */}
      <h2 className="vault-heading text-sm mb-3 mt-8 flex items-center gap-2">
        <FileText size={14} /> Cost Summary
      </h2>
      <VaultCard>
        {overviewLoading ? (
          <div className="flex items-center justify-center gap-2 py-6">
            <Loader2 size={16} className="animate-spin text-cold-teal" />
            <span className="text-bone-muted font-mono text-sm">Loading cost data...</span>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">
                Total Governance Cost
              </p>
              <p className="text-3xl font-heading font-bold text-bone font-mono mt-1">
                ${((overview?.total_cost_usd as number) ?? 0).toFixed(4)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs font-heading uppercase tracking-wider text-bone-muted">
                Environment
              </p>
              <p className="text-sm text-bone font-mono mt-1">
                {(overview?.environment as string) ?? "---"}
              </p>
            </div>
          </div>
        )}
      </VaultCard>

      {/* Audit timeline */}
      <h2 className="vault-heading text-sm mb-3 mt-8 flex items-center gap-2">
        <Clock size={14} /> Audit Timeline
      </h2>
      <VaultCard>
        {overviewLoading ? (
          <div className="flex items-center justify-center gap-2 py-6">
            <Loader2 size={16} className="animate-spin text-cold-teal" />
            <span className="text-bone-muted font-mono text-sm">Loading audit events...</span>
          </div>
        ) : !(overview?.recent_activity as unknown[])?.length ? (
          <p className="text-bone-dim font-mono text-sm py-4 text-center">
            No audit events recorded
          </p>
        ) : (
          <div className="divide-y divide-slate-border/50">
            {(overview?.recent_activity as Record<string, unknown>[])?.map(
              (event, i: number) => (
                <div
                  key={i}
                  className="flex items-center gap-4 px-4 py-3 hover:bg-wet-stone/30 transition-colors"
                >
                  <div className="w-1.5 h-1.5 rounded-full bg-cold-teal flex-shrink-0" />
                  <MonoText className="text-xs w-36 flex-shrink-0">
                    {formatTimestamp(event.created_at as string | null)}
                  </MonoText>
                  <span className="text-xs text-bone-muted font-mono w-24 flex-shrink-0">
                    {(event.actor as string) ?? (event.source as string) ?? "system"}
                  </span>
                  <span className="text-sm text-bone flex-1">
                    {(event.action as string) ?? (event.event_type as string)}
                  </span>
                </div>
              ),
            )}
          </div>
        )}
      </VaultCard>
    </div>
  );
}
