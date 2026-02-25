export function GateProgress({
  passed,
  total,
  className = "",
}: {
  passed: number;
  total: number;
  className?: string;
}) {
  const pct = total > 0 ? (passed / total) * 100 : 0;
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="progress-vault flex-1">
        <div className="progress-vault-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-bone-muted whitespace-nowrap">
        {passed}/{total}
      </span>
    </div>
  );
}
