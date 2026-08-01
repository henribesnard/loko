/**
 * LOKO Monitoring — Improvement signals panel (green-tinted).
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { IntentDetail, KPIOverview } from "@/hooks/useBotMonitoring";

interface SignalsPanelProps {
  overview: KPIOverview;
  intents: IntentDetail[];
}

export function SignalsPanel({ overview, intents }: SignalsPanelProps) {
  const { t } = useTranslation();

  const signals = useMemo(() => {
    const result: string[] = [];

    // High guardrail / out-of-scope rate
    if (overview.messages > 0) {
      const oosRate = overview.guardrail_blocks / overview.messages;
      if (oosRate > 0.08) {
        result.push(
          t("monitoring.signals.highOos", {
            defaultValue: `Le taux de hors-périmètre est de ${Math.round(oosRate * 100)}% — envisagez d'élargir le périmètre annoncé en accueil si ces demandes sont fréquentes.`,
          }),
        );
      }
    }

    // Low selfcare intents
    const lowSelfcare = intents.filter(
      (i) => i.volume >= 20 && i.selfcare_rate < 0.65,
    );
    for (const intent of lowSelfcare.slice(0, 2)) {
      result.push(
        t("monitoring.signals.lowSelfcare", {
          defaultValue: `« ${intent.intent_id} » a un selfcare de ${Math.round(intent.selfcare_rate * 100)}%, en retrait — la matrice de confusion suggère d'ajouter des exemples discriminants.`,
        }),
      );
    }

    // High error rate
    if (overview.error_rate > 0.05) {
      result.push(
        t("monitoring.signals.highErrors", {
          defaultValue: `Le taux d'erreur est de ${(overview.error_rate * 100).toFixed(1)}% — vérifiez les logs pour identifier les causes récurrentes.`,
        }),
      );
    }

    return result;
  }, [overview, intents, t]);

  if (signals.length === 0) return null;

  return (
    <div
      className="rounded-[var(--radius-lg)] p-5"
      style={{
        background: "var(--brand-primary-tint)",
        border: "1px solid var(--brand-primary-border, var(--border-subtle))",
      }}
    >
      <div
        className="text-[13.5px] font-semibold mb-3"
        style={{ color: "var(--green-700)" }}
      >
        {t("monitoring.signals.title", "Signaux d'amélioration")}
      </div>
      <div className="flex flex-col gap-2.5">
        {signals.map((text, i) => (
          <div
            key={i}
            className="text-xs leading-snug"
            style={{ color: "var(--green-700)" }}
          >
            — {text}
          </div>
        ))}
      </div>
    </div>
  );
}
