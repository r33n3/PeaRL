import { useState } from "react";
import { ChevronDown, ChevronRight, Shield } from "lucide-react";
import { VaultCard } from "@/components/shared/VaultCard";
import { useRecommendedGuardrails } from "@/api/guardrails";
import type { GuardrailRecommendation, BedrockConfig, CedarPolicy } from "@/api/guardrails";

interface GuardrailsTabProps {
  projectId: string | undefined;
}

// ── Severity dot ─────────────────────────────────────────────────────────────

function SeverityDot({ severity }: { severity: string }) {
  const color =
    severity === "critical" ? "bg-red-500" :
    severity === "high" ? "bg-orange-400" :
    severity === "moderate" ? "bg-yellow-400" :
    "bg-green-400";
  return <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${color}`} />;
}

// ── Platform type badges in the header strip ──────────────────────────────────

function ProjectTypeBadge({ type }: { type: string }) {
  const lower = type.toLowerCase();
  const cls =
    lower === "agent"
      ? "bg-purple-500/20 text-purple-300 border-purple-500/30"
      : lower === "ai application" || lower === "ai_application"
      ? "bg-blue-500/20 text-blue-300 border-blue-500/30"
      : "bg-white/10 text-white/60 border-white/10";
  const label =
    lower === "ai_application" ? "AI Application" :
    lower === "agent" ? "Agent" :
    type;
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${cls}`}>{label}</span>
  );
}

function PlatformTag({ platform }: { platform: string }) {
  const lower = platform.toLowerCase();
  const cls =
    lower === "bedrock"
      ? "bg-orange-500/20 text-orange-300 border-orange-500/30"
      : lower === "cedar"
      ? "bg-purple-500/20 text-purple-300 border-purple-500/30"
      : lower === "agentcore"
      ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
      : "bg-white/10 text-white/60 border-white/10";
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${cls}`}>{platform}</span>
  );
}

// ── Code block ────────────────────────────────────────────────────────────────

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-black/40 font-mono text-xs text-green-400 p-3 rounded overflow-x-auto whitespace-pre-wrap">
      {children}
    </pre>
  );
}

// ── Platform config tabs inside a card ───────────────────────────────────────

type PlatformTab = "bedrock" | "cedar" | "implementation";

function PlatformTabs({
  bedrockConfig,
  cedarPolicy,
  steps,
  codeExamples,
}: {
  bedrockConfig?: BedrockConfig;
  cedarPolicy?: CedarPolicy;
  steps: string[];
  codeExamples?: Record<string, string>;
}) {
  const tabs: { id: PlatformTab; label: string }[] = [];
  if (bedrockConfig) tabs.push({ id: "bedrock", label: "Bedrock Config" });
  if (cedarPolicy) tabs.push({ id: "cedar", label: "Cedar Policy" });
  if (codeExamples?.python || steps.length > 0) {
    tabs.push({ id: "implementation", label: "Implementation" });
  }

  const [active, setActive] = useState<PlatformTab>(tabs[0]?.id ?? "implementation");

  if (tabs.length === 0) return null;

  return (
    <div className="mt-3">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-white/10 mb-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActive(t.id)}
            className={`text-xs font-mono px-3 py-1.5 border-b-2 transition-colors ${
              active === t.id
                ? "border-purple-500 text-purple-400"
                : "border-transparent text-white/50 hover:text-white/70"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {active === "bedrock" && bedrockConfig && (
        <div>
          {bedrockConfig.note ? (
            <p className="text-xs font-mono text-amber-300/80 bg-amber-500/10 border border-amber-500/20 p-3 rounded">
              {bedrockConfig.note}
            </p>
          ) : (
            <CodeBlock>
              {JSON.stringify(bedrockConfig, null, 2)}
            </CodeBlock>
          )}
        </div>
      )}

      {active === "cedar" && cedarPolicy && (
        <div>
          <p className="text-[10px] font-mono text-white/40 mb-1">{cedarPolicy.policy_id}</p>
          <CodeBlock>{cedarPolicy.statement}</CodeBlock>
        </div>
      )}

      {active === "implementation" && (
        <div>
          {codeExamples?.python ? (
            <CodeBlock>{codeExamples.python}</CodeBlock>
          ) : (
            <ol className="space-y-1.5 list-decimal list-inside">
              {steps.map((step, i) => (
                <li key={i} className="text-xs font-mono text-white/70">
                  {step}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

// ── Single guardrail card ─────────────────────────────────────────────────────

function GuardrailCard({ rec }: { rec: GuardrailRecommendation }) {
  const [stepsOpen, setStepsOpen] = useState(false);
  const hasPlatformConfig = !!(rec.bedrock_config || rec.cedar_policy);

  return (
    <VaultCard>
      {/* Name row */}
      <div className="flex items-center gap-2 mb-2">
        <SeverityDot severity={rec.severity} />
        <span className="text-sm font-heading text-white font-semibold">{rec.name}</span>
        <span className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-white/50 border border-white/10">
          {rec.category}
        </span>
      </div>

      {/* Description */}
      <p className="text-xs font-mono text-white/60 leading-relaxed mb-3">
        {rec.description}
      </p>

      {/* Platform tabs (Bedrock / Cedar / Implementation) */}
      {hasPlatformConfig ? (
        <PlatformTabs
          bedrockConfig={rec.bedrock_config}
          cedarPolicy={rec.cedar_policy}
          steps={rec.implementation_steps}
          codeExamples={rec.code_examples}
        />
      ) : (
        /* No platform config — show collapsible steps inline */
        rec.implementation_steps.length > 0 && (
          <div>
            <button
              className="flex items-center gap-1.5 text-xs font-mono text-white/50 hover:text-white/70 transition-colors mb-2"
              onClick={() => setStepsOpen((v) => !v)}
            >
              {stepsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Implementation Steps
            </button>
            {stepsOpen && (
              <ol className="space-y-1.5 list-decimal list-inside pl-1">
                {rec.implementation_steps.map((step, i) => (
                  <li key={i} className="text-xs font-mono text-white/70">
                    {step}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )
      )}
    </VaultCard>
  );
}

// ── Main tab component ────────────────────────────────────────────────────────

export function GuardrailsTab({ projectId }: GuardrailsTabProps) {
  const { data, isLoading, error } = useRecommendedGuardrails(projectId);

  if (isLoading) {
    return (
      <div className="space-y-3 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded bg-white/5 border border-white/10" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-xs font-mono text-red-400 p-4 bg-red-500/10 border border-red-500/20 rounded">
        Failed to load guardrail recommendations.
      </div>
    );
  }

  if (!data) return null;

  const { project_type, target_platforms, open_findings_count, recommended_guardrails } = data;

  return (
    <div>
      {/* Header strip */}
      <div className="flex flex-wrap items-center gap-2 mb-6 p-3 bg-white/5 border border-white/10 rounded">
        <ProjectTypeBadge type={project_type} />
        {target_platforms.map((p) => (
          <PlatformTag key={p} platform={p} />
        ))}
        <span className="ml-auto text-xs font-mono text-white/50 flex items-center gap-1.5">
          <Shield size={12} />
          {open_findings_count} open finding{open_findings_count !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Guardrail cards */}
      {recommended_guardrails.length === 0 ? (
        <div className="text-center py-12 text-xs font-mono text-white/40">
          No guardrail recommendations — run a scan first to generate tailored recommendations.
        </div>
      ) : (
        <div className="space-y-3">
          {recommended_guardrails.map((rec) => (
            <GuardrailCard key={rec.id} rec={rec} />
          ))}
        </div>
      )}
    </div>
  );
}
