/**
 * LOKO Monitoring — Control bar with period pills, compare toggle,
 * granularity switch, and CSV export dropdown.
 */
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import type { ExportView, Granularity, Period } from "@/hooks/useBotMonitoring";

interface ControlBarProps {
  period: Period;
  onPeriod: (p: Period) => void;
  compare: boolean;
  onCompare: (v: boolean) => void;
  granularity: Granularity;
  onGranularity: (g: Granularity) => void;
  onExport: (view: ExportView) => void;
}

const PERIODS: Period[] = ["7d", "30d", "90d"];
const GRANULARITY_KEYS: Granularity[] = ["hour", "day"];
const EXPORT_KEYS: ExportView[] = ["overview", "intents", "sub_motifs"];

export function ControlBar({
  period,
  onPeriod,
  compare,
  onCompare,
  granularity,
  onGranularity,
  onExport,
}: ControlBarProps) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  return (
    <div
      className="sticky top-0 z-10 flex items-center justify-between flex-wrap gap-3 px-7 py-3 border-b"
      style={{
        background: "var(--surface-card)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div className="flex items-center gap-4 flex-wrap">
        {/* Period pills */}
        <div className="flex gap-1.5">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => onPeriod(p)}
              className={cn(
                "px-3.5 py-1.5 rounded-full text-xs font-medium border transition-colors cursor-pointer",
                period === p
                  ? "border-brand-500 bg-[var(--brand-primary-tint)] text-[var(--green-700)]"
                  : "border-[var(--border-default)] bg-transparent text-[var(--text-secondary)]",
              )}
            >
              {t(`monitoring.period.${p}`)}
            </button>
          ))}
        </div>

        {/* Compare toggle */}
        <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={compare}
            onChange={() => onCompare(!compare)}
            className="accent-brand-500"
          />
          {t("monitoring.compare")}
        </label>

        {/* Granularity */}
        <div
          className="flex gap-0.5 rounded-[var(--radius-sm)] p-0.5"
          style={{ background: "var(--surface-sunken)" }}
        >
          {GRANULARITY_KEYS.map((g) => (
            <button
              key={g}
              onClick={() => onGranularity(g)}
              className={cn(
                "px-3 py-1 rounded-[5px] border-none text-xs font-medium cursor-pointer transition-colors",
                granularity === g
                  ? "bg-[var(--surface-card)] text-[var(--text-primary)]"
                  : "bg-transparent text-[var(--text-tertiary)]",
              )}
            >
              {t(`monitoring.granularity.${g}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Export dropdown */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="text-xs font-semibold px-3.5 py-2 rounded-[var(--radius-sm)] border bg-transparent cursor-pointer"
          style={{
            borderColor: "var(--border-default)",
            color: "var(--text-primary)",
          }}
        >
          {t("monitoring.exportCsv", "Exporter CSV")} &#x25BE;
        </button>
        {menuOpen && (
          <div
            className="absolute right-0 top-9 w-48 rounded-[var(--radius-md)] p-1.5 z-20"
            style={{
              background: "var(--surface-card)",
              border: "1px solid var(--border-subtle)",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            {EXPORT_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => {
                  onExport(key);
                  setMenuOpen(false);
                }}
                className="w-full text-left px-2.5 py-2 border-none bg-transparent rounded-[var(--radius-sm)] text-xs cursor-pointer hover:bg-[var(--surface-sunken)]"
                style={{ color: "var(--text-primary)" }}
              >
                {t(`monitoring.export.${key}`)}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
