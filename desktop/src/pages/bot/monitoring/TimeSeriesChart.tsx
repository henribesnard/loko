/**
 * LOKO Monitoring — Multi-line SVG time series chart.
 *
 * Shows conversations, selfcare, escalations, + optional N-1 dashed line.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TimeseriesBucket } from "@/hooks/useBotMonitoring";

interface TimeSeriesChartProps {
  data: TimeseriesBucket[];
  prevData: TimeseriesBucket[];
  compare: boolean;
}

const W = 760;
const H = 200;

function toPolyline(values: number[], maxVal: number): string {
  if (values.length < 2) return "";
  return values
    .map((v, i) => `${(i / (values.length - 1)) * W},${H - (v / maxVal) * H}`)
    .join(" ");
}

export function TimeSeriesChart({
  data,
  prevData,
  compare,
}: TimeSeriesChartProps) {
  const { t } = useTranslation();

  const { main, selfcare, escalations, prev, areaPoints } =
    useMemo(() => {
      const sessions = data.map((b) => b.sessions);
      const sc = data.map((b) => b.answers);
      const esc = data.map((b) => b.escalations);
      const prevSessions = prevData.map((b) => b.sessions);

      const allVals = [...sessions, ...sc, ...esc];
      if (compare) allVals.push(...prevSessions);
      const max = Math.max(...allVals, 1) * 1.15;

      const mainPoly = toPolyline(sessions, max);
      const area =
        sessions.length >= 2
          ? `0,${H} ${mainPoly} ${W},${H}`
          : "";

      return {
        main: mainPoly,
        selfcare: toPolyline(sc, max),
        escalations: toPolyline(esc, max),
        prev: toPolyline(prevSessions, max),
        maxVal: max,
        areaPoints: area,
      };
    }, [data, prevData, compare]);

  if (data.length === 0) return null;

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
          {t("monitoring.chartTitle", "Volume de conversations")}
        </div>
        <div className="flex gap-3.5 text-[11.5px]" style={{ color: "var(--text-tertiary)" }}>
          <Legend color="var(--brand-primary)" label="Conversations" />
          <Legend color="var(--info-fg)" label="Selfcare" />
          <Legend color="var(--warning-fg)" label="Escalades" />
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 220 }}>
        {compare && prev && (
          <polyline
            points={prev}
            fill="none"
            stroke="var(--text-tertiary)"
            strokeWidth={1.6}
            strokeDasharray="4 4"
            opacity={0.5}
          />
        )}
        {areaPoints && (
          <polygon points={areaPoints} fill="var(--brand-primary)" opacity={0.08} />
        )}
        <polyline
          points={main}
          fill="none"
          stroke="var(--brand-primary)"
          strokeWidth={2}
        />
        <polyline
          points={selfcare}
          fill="none"
          stroke="var(--info-fg)"
          strokeWidth={1.6}
        />
        <polyline
          points={escalations}
          fill="none"
          stroke="var(--warning-fg)"
          strokeWidth={1.6}
        />
      </svg>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="inline-block"
        style={{ width: 9, height: 3, background: color }}
      />
      {label}
    </span>
  );
}
