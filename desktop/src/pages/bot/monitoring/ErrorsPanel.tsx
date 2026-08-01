/**
 * LOKO Monitoring — Errors list panel with sparklines.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { KPIOverview } from "@/hooks/useBotMonitoring";

interface ErrorsPanelProps {
  overview: KPIOverview;
}

interface ErrorRow {
  label: string;
  count: number;
}

export function ErrorsPanel({ overview }: ErrorsPanelProps) {
  const { t } = useTranslation();

  const errors: ErrorRow[] = useMemo(
    () => [
      {
        label: t("monitoring.errors.unavailable", "Réponse indisponible"),
        count: overview.errors,
      },
      {
        label: t("monitoring.errors.outOfScope", "Hors périmètre"),
        count: overview.guardrail_blocks,
      },
    ],
    [overview, t],
  );

  return (
    <div
      className="rounded-[var(--radius-lg)] p-5"
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <div className="flex items-center justify-between mb-3.5">
        <div
          className="text-[13.5px] font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          {t("monitoring.errors.title", "Erreurs")}
        </div>
      </div>
      <div className="flex flex-col gap-0.5">
        {errors.map((e) => (
          <div
            key={e.label}
            className="flex items-center justify-between py-2.5 border-t text-xs"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <span style={{ color: "var(--text-primary)" }}>{e.label}</span>
            <span
              className="font-mono"
              style={{ color: "var(--text-tertiary)" }}
            >
              {e.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
