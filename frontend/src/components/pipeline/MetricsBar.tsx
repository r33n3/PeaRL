import { AreaChart, Area, ResponsiveContainer, Tooltip } from "recharts";
import { TrendingDown, AlertTriangle, DollarSign } from "lucide-react";
import type { PortfolioMetrics } from "@/lib/types";

interface Props {
  metrics: PortfolioMetrics;
}

export function MetricsBar({ metrics }: Props) {
  const {
    drift_series,
    mttr_days,
    mttr_trend,
    mtte_days,
    velocity_new_7d,
    velocity_resolved_7d,
    blocked_projects,
    open_findings_total,
    open_critical,
    open_high,
    total_pearl_cost_usd,
  } = metrics;

  const driftIsAccumulating = drift_series.some((d) => d.net > 0);
  const driftColor = driftIsAccumulating ? "#7f1d1d" : "#39a99e";
  const driftFill = driftIsAccumulating ? "#7f1d1d33" : "#39a99e22";

  return (
    <div className="border-t border-slate-border bg-charcoal/80 px-6 py-3 flex items-center gap-5 flex-shrink-0 overflow-x-auto">
      {/* PeaRL Cost total */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px] flex items-center gap-1">
          <DollarSign size={10} />
          PeaRL Cost
        </p>
        <p className="mono-data text-lg leading-none">
          ${(total_pearl_cost_usd ?? 0).toFixed(2)}
        </p>
        <p className="text-[9px] font-mono text-bone-dim">all projects</p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* Drift sparkline */}
      <div className="flex flex-col gap-1 w-36 flex-shrink-0">
        <p className="vault-heading text-[10px]">Temporal Drift</p>
        <div className="h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={drift_series}
              margin={{ top: 2, right: 0, bottom: 2, left: 0 }}
            >
              <Area
                type="monotone"
                dataKey="net"
                stroke={driftColor}
                fill={driftFill}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1f24",
                  border: "1px solid #2a3540",
                  borderRadius: "6px",
                  fontSize: "10px",
                  fontFamily: "monospace",
                  padding: "4px 8px",
                }}
                labelFormatter={(label) => String(label)}
                formatter={(val: number) => [val > 0 ? `+${val}` : val, "net"]}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <p className="text-[9px] font-mono text-bone-dim">7-day net delta</p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* MTTR */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px]">MTTR</p>
        <p className="mono-data text-lg leading-none">
          {mttr_days != null ? `${mttr_days}d` : "—"}
        </p>
        <p
          className={`text-[10px] font-mono ${
            mttr_trend === "improving"
              ? "text-cold-teal"
              : mttr_trend === "worsening"
              ? "text-dried-blood-bright"
              : "text-bone-dim"
          }`}
        >
          {mttr_trend}
        </p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* MTTE */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px]">MTTE</p>
        <p className="mono-data text-lg leading-none">
          {mtte_days != null ? `${mtte_days}d` : "—"}
        </p>
        <p className="text-[10px] font-mono text-bone-dim">avg promotion</p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* Velocity */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px] flex items-center gap-1">
          <TrendingDown size={10} />
          7-Day Velocity
        </p>
        <p className="mono-data text-sm leading-tight">+{velocity_new_7d} new</p>
        <p className="text-sm font-mono text-cold-teal leading-tight">
          -{velocity_resolved_7d} resolved
        </p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* Blocked projects */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px]">Blocked</p>
        <p
          className={`mono-data text-lg leading-none ${
            blocked_projects > 0 ? "text-dried-blood-bright" : "text-cold-teal"
          }`}
        >
          {blocked_projects}
        </p>
        <p className="text-[10px] font-mono text-bone-dim">projects</p>
      </div>

      <div className="w-px h-10 bg-slate-border flex-shrink-0" />

      {/* Open findings */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <p className="vault-heading text-[10px] flex items-center gap-1">
          <AlertTriangle size={10} />
          Open Findings
        </p>
        <p className="mono-data text-lg leading-none">{open_findings_total}</p>
        <p className="text-[10px] font-mono text-bone-dim leading-tight">
          {open_critical > 0 && (
            <span className="text-dried-blood-bright">{open_critical}C </span>
          )}
          {open_high > 0 && (
            <span className="text-orange-400">{open_high}H</span>
          )}
          {open_critical === 0 && open_high === 0 && "all clear"}
        </p>
      </div>
    </div>
  );
}
