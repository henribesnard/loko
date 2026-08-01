interface QuotaBarProps {
  label: string;
  used: number;
  limit: number;
}

export function QuotaBar({ label, used, limit }: QuotaBarProps) {
  const ratio = limit > 0 ? used / limit : 0;
  const pct = Math.min(ratio * 100, 100);
  const color =
    ratio >= 1 ? "var(--error-fg)" : ratio >= 0.8 ? "var(--warning-fg)" : "var(--brand-primary)";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span style={{ color: "var(--text-secondary)" }}>{label}</span>
        <span style={{ color: "var(--text-primary)" }} className="font-medium">
          {used} / {limit >= 999_999 ? "\u221E" : limit}
        </span>
      </div>
      <div
        className="h-2 w-full overflow-hidden"
        style={{ borderRadius: "var(--radius-xs)", background: "var(--surface-sunken)" }}
      >
        <div
          className="h-full transition-all"
          style={{
            width: `${pct}%`,
            background: color,
            borderRadius: "var(--radius-xs)",
          }}
        />
      </div>
    </div>
  );
}
