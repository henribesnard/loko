/**
 * LOKO Monitoring — KPI cards grid with sparklines and deltas.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { KPIOverview, TimeseriesBucket } from "@/hooks/useBotMonitoring";

interface KPICardsProps {
  overview: KPIOverview;
  prevOverview: KPIOverview | null;
  timeseries: TimeseriesBucket[];
  compare: boolean;
}

interface CardData {
  label: string;
  value: string;
  sparkValues: number[];
  delta: number | null;
  invertDelta?: boolean; // true = decrease is good (escalations, errors)
}

function sparklinePoints(values: number[], w: number, h: number): string {
  if (values.length < 2) return "";
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  return values
    .map(
      (v, i) =>
        `${(i / (values.length - 1)) * w},${h - ((v - min) / range) * h}`,
    )
    .join(" ");
}

export function KPICards({
  overview,
  prevOverview,
  timeseries,
  compare,
}: KPICardsProps) {
  const { t } = useTranslation();

  const cards: CardData[] = useMemo(() => {
    const prev = prevOverview;
    const sessionsData = timeseries.map((b) => b.sessions);
    const messagesData = timeseries.map((b) => b.messages);
    const answersData = timeseries.map((b) => b.answers);
    const escalationsData = timeseries.map((b) => b.escalations);
    const errorsData = timeseries.map((b) => b.errors);
    const satisfactionData = timeseries.map((b) => {
      const total = b.feedback_up + b.feedback_down;
      return total > 0 ? b.feedback_up / total : 0;
    });

    function delta(curr: number, prevVal: number | undefined): number | null {
      if (!compare || prevVal == null || prevVal === 0) return null;
      return (curr - prevVal) / prevVal;
    }

    return [
      {
        label: t("monitoring.kpi.sessions", "Conversations totales"),
        value: overview.sessions.toLocaleString("fr-FR"),
        sparkValues: sessionsData,
        delta: delta(overview.sessions, prev?.sessions),
      },
      {
        label: t("monitoring.kpi.messages", "Messages"),
        value: overview.messages.toLocaleString("fr-FR"),
        sparkValues: messagesData,
        delta: delta(overview.messages, prev?.messages),
      },
      {
        label: t("monitoring.kpi.selfcare", "Taux de selfcare"),
        value: `${Math.round(overview.selfcare_rate * 100)} %`,
        sparkValues: answersData,
        delta: delta(overview.selfcare_rate, prev?.selfcare_rate),
      },
      {
        label: t("monitoring.kpi.escalations", "Escalades"),
        value: overview.escalations.toLocaleString("fr-FR"),
        sparkValues: escalationsData,
        delta: delta(overview.escalations, prev?.escalations),
        invertDelta: true,
      },
      {
        label: t("monitoring.kpi.errors", "Erreurs"),
        value: overview.errors.toLocaleString("fr-FR"),
        sparkValues: errorsData,
        delta: delta(overview.errors, prev?.errors),
        invertDelta: true,
      },
      {
        label: t("monitoring.kpi.satisfaction", "Satisfaction"),
        value: `${Math.round(overview.satisfaction_rate * 100)} %`,
        sparkValues: satisfactionData,
        delta: delta(overview.satisfaction_rate, prev?.satisfaction_rate),
      },
    ];
  }, [overview, prevOverview, timeseries, compare, t]);

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-[var(--radius-lg)] p-3.5"
          style={{
            background: "var(--surface-card)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div
            className="text-[10.5px] mb-2"
            style={{ color: "var(--text-tertiary)" }}
          >
            {card.label}
          </div>
          <div
            className="font-mono text-[19px] font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {card.value}
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <svg width={52} height={16} viewBox="0 0 52 16">
              <polyline
                points={sparklinePoints(card.sparkValues, 52, 16)}
                fill="none"
                stroke="var(--brand-primary)"
                strokeWidth={1.6}
              />
            </svg>
            {card.delta !== null && (
              <DeltaBadge
                delta={card.delta}
                invert={card.invertDelta}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function DeltaBadge({
  delta,
  invert,
}: {
  delta: number;
  invert?: boolean;
}) {
  const positive = delta >= 0;
  const good = invert ? !positive : positive;
  const color = good ? "var(--success-fg)" : "var(--error-fg)";
  const label = `${positive ? "+" : ""}${(delta * 100).toFixed(1)}%`;

  return (
    <span
      className="font-mono text-[10.5px] font-semibold"
      style={{ color }}
    >
      {label}
    </span>
  );
}
