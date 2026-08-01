/**
 * LOKO Monitoring — 5-step horizontal funnel visualization.
 */
import { useTranslation } from "react-i18next";
import type { FunnelStep } from "@/hooks/useBotMonitoring";

interface FunnelChartProps {
  steps: FunnelStep[];
}

const STEP_KEYS: Record<string, string> = {
  messages: "monitoring.funnel.received",
  classified: "monitoring.funnel.classified",
  answered: "monitoring.funnel.answered",
  surveyed: "monitoring.funnel.surveyed",
  resolved: "monitoring.funnel.resolved",
};

export function FunnelChart({ steps }: FunnelChartProps) {
  const { t } = useTranslation();

  if (steps.length === 0) return null;

  return (
    <div
      className="rounded-[var(--radius-lg)] p-5"
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <div
        className="text-[13.5px] font-semibold mb-4"
        style={{ color: "var(--text-primary)" }}
      >
        {t("monitoring.funnel.title", "Entonnoir")}
      </div>
      <div className="flex items-stretch gap-0.5">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          return (
            <div
              key={step.step}
              className="flex-1 flex flex-col items-center gap-2"
            >
              <div
                className="w-full rounded-lg flex items-center justify-center flex-col"
                style={{
                  height: 64,
                  background: isLast
                    ? "var(--success-bg)"
                    : "var(--brand-primary-tint)",
                }}
              >
                <span
                  className="font-mono text-[15px] font-semibold"
                  style={{
                    color: isLast ? "var(--success-fg)" : "var(--green-700)",
                  }}
                >
                  {step.count.toLocaleString("fr-FR")}
                </span>
              </div>
              <div
                className="text-[11.5px] font-semibold text-center"
                style={{ color: "var(--text-primary)" }}
              >
                {STEP_KEYS[step.step] ? t(STEP_KEYS[step.step]) : step.step}
              </div>
              {i > 0 && (
                <div
                  className="font-mono text-[10.5px]"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {Math.round(step.rate * 100)}%
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
