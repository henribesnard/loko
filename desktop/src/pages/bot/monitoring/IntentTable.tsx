/**
 * LOKO Monitoring — Sortable intent table with breadcrumb drill-down.
 */
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import type {
  IntentDetail,
  SortColumn,
  SortDir,
  SubMotif,
} from "@/hooks/useBotMonitoring";

interface IntentTableProps {
  intents: IntentDetail[];
  subMotifs: SubMotif[];
  totalVolume: number;
  drilledIntent: string | null;
  sortColumn: SortColumn;
  sortDir: SortDir;
  onSort: (col: SortColumn) => void;
  onDrill: (intentId: string) => void;
  onDrillUp: () => void;
  botId: string;
}

interface Column {
  key: SortColumn | "share" | "trend_spark";
  label: string;
  sortable: boolean;
  sortKey?: SortColumn;
}

const COLUMNS: Column[] = [
  { key: "intent_id", label: "Intention", sortable: true, sortKey: "intent_id" },
  { key: "volume", label: "Volume", sortable: true, sortKey: "volume" },
  { key: "share", label: "Part", sortable: false },
  { key: "selfcare_rate", label: "Selfcare", sortable: true, sortKey: "selfcare_rate" },
  { key: "clarifications", label: "Clarif.", sortable: true, sortKey: "clarifications" },
  { key: "escalations", label: "Escal.", sortable: true, sortKey: "escalations" },
  { key: "avg_confidence", label: "Confiance", sortable: true, sortKey: "avg_confidence" },
  { key: "trend_spark", label: "Tendance", sortable: false },
];

function sparkline(trend: number): string {
  // Simplified sparkline from trend delta: just a visual indicator
  const base = 7;
  const pts = [
    `0,${base}`,
    `12,${base - trend * 4}`,
    `23,${base + trend * 2}`,
    `35,${base - trend * 6}`,
    `46,${base - trend * 8}`,
  ];
  return pts.join(" ");
}

export function IntentTable({
  intents,
  subMotifs,
  totalVolume,
  drilledIntent,
  sortColumn,
  sortDir,
  onSort,
  onDrill,
  onDrillUp,
  botId,
}: IntentTableProps) {
  const { t } = useTranslation();

  return (
    <div
      className="rounded-[var(--radius-lg)] p-5"
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      {/* Breadcrumb */}
      <div
        className="flex items-center gap-2 mb-4 text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        <button
          onClick={onDrillUp}
          className={cn(
            "bg-transparent border-none p-0 cursor-pointer text-xs",
            drilledIntent
              ? "font-medium"
              : "font-semibold",
          )}
          style={{
            color: drilledIntent
              ? "var(--text-link)"
              : "var(--text-primary)",
          }}
        >
          {t("monitoring.intents.title", "Intentions")}
        </button>
        {drilledIntent && (
          <>
            <span>&rsaquo;</span>
            <span
              className="font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {drilledIntent}
            </span>
            <span>&rsaquo;</span>
            <span
              className="font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {t("monitoring.intents.subMotifs", "Sous-motifs")}
            </span>
          </>
        )}
      </div>

      <div className="grid grid-cols-[1fr_220px] gap-5">
        {/* Table */}
        <div className="overflow-x-auto">
          {/* Header */}
          <div
            className="grid gap-1 px-2.5 py-2 border-b"
            style={{
              gridTemplateColumns:
                "1.4fr 0.7fr 0.6fr 0.8fr 0.8fr 0.8fr 0.9fr 0.8fr",
              borderColor: "var(--border-subtle)",
            }}
          >
            {COLUMNS.map((col) => (
              <button
                key={col.key}
                onClick={
                  col.sortable && col.sortKey
                    ? () => onSort(col.sortKey!)
                    : undefined
                }
                className="text-left bg-transparent border-none p-0 text-[10.5px] font-semibold uppercase tracking-wide cursor-pointer"
                style={{
                  color:
                    col.sortKey && sortColumn === col.sortKey
                      ? "var(--text-primary)"
                      : "var(--text-tertiary)",
                }}
              >
                {col.label}{" "}
                {col.sortKey && sortColumn === col.sortKey
                  ? sortDir === "desc"
                    ? "\u2193"
                    : "\u2191"
                  : ""}
              </button>
            ))}
          </div>

          {/* Rows */}
          {drilledIntent
            ? subMotifs.map((sm) => (
                <SubMotifRow
                  key={sm.sub_motif_id}
                  sm={sm}
                  totalVolume={totalVolume}
                />
              ))
            : intents.map((intent) => (
                <IntentRow
                  key={intent.intent_id}
                  intent={intent}
                  totalVolume={totalVolume}
                  onDrill={onDrill}
                />
              ))}

          {/* Drill-down link */}
          {drilledIntent && (
            <div className="px-2.5 py-3">
              <a
                href={`/bot/${botId}/dashboard`}
                className="text-xs font-medium"
                style={{ color: "var(--text-link)" }}
              >
                {t("monitoring.intents.viewConversations", "Voir les conversations")} &rarr;
              </a>
            </div>
          )}
        </div>

        {/* Distribution sidebar */}
        <DistributionBars intents={intents} totalVolume={totalVolume} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function IntentRow({
  intent,
  totalVolume,
  onDrill,
}: {
  intent: IntentDetail;
  totalVolume: number;
  onDrill: (id: string) => void;
}) {
  const share =
    totalVolume > 0
      ? `${Math.round((intent.volume / totalVolume) * 100)}%`
      : "0%";
  const selfcareLow = intent.selfcare_rate < 0.5;
  const confLow =
    intent.avg_confidence !== null && intent.avg_confidence < 0.8;

  return (
    <div
      onClick={() => onDrill(intent.intent_id)}
      className="grid gap-1 px-2.5 py-2.5 border-b items-center cursor-pointer hover:bg-[var(--surface-sunken)] transition-colors"
      style={{
        gridTemplateColumns:
          "1.4fr 0.7fr 0.6fr 0.8fr 0.8fr 0.8fr 0.9fr 0.8fr",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div
        className="text-xs truncate"
        style={{ color: "var(--text-primary)" }}
      >
        {intent.intent_id}
      </div>
      <div className="font-mono text-xs">
        {intent.volume.toLocaleString("fr-FR")}
      </div>
      <div
        className="font-mono text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        {share}
      </div>
      <div
        className="font-mono text-xs"
        style={{
          color: selfcareLow ? "var(--warning-fg)" : "var(--text-primary)",
        }}
      >
        {Math.round(intent.selfcare_rate * 100)}%
      </div>
      <div
        className="font-mono text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        {intent.clarifications}
      </div>
      <div
        className="font-mono text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        {intent.escalations}
      </div>
      <div
        className="font-mono text-xs"
        style={{
          color: confLow ? "var(--warning-fg)" : "var(--text-primary)",
        }}
      >
        {intent.avg_confidence !== null
          ? intent.avg_confidence.toFixed(2)
          : "—"}
      </div>
      <svg width={46} height={14} viewBox="0 0 46 14">
        <polyline
          points={sparkline(intent.trend)}
          fill="none"
          stroke="var(--text-tertiary)"
          strokeWidth={1.4}
        />
      </svg>
    </div>
  );
}

function SubMotifRow({
  sm,
  totalVolume,
}: {
  sm: SubMotif;
  totalVolume: number;
}) {
  const share =
    totalVolume > 0
      ? `${Math.round((sm.volume / totalVolume) * 100)}%`
      : "0%";
  const selfcareLow = sm.selfcare_rate < 0.5;

  return (
    <div
      className="grid gap-1 px-2.5 py-2.5 border-b items-center"
      style={{
        gridTemplateColumns:
          "1.4fr 0.7fr 0.6fr 0.8fr 0.8fr 0.8fr 0.9fr 0.8fr",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div
        className="text-xs truncate"
        style={{ color: "var(--text-primary)" }}
      >
        {sm.sub_motif_id}
      </div>
      <div className="font-mono text-xs">
        {sm.volume.toLocaleString("fr-FR")}
      </div>
      <div
        className="font-mono text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        {share}
      </div>
      <div
        className="font-mono text-xs"
        style={{
          color: selfcareLow ? "var(--warning-fg)" : "var(--text-primary)",
        }}
      >
        {Math.round(sm.selfcare_rate * 100)}%
      </div>
      <div className="font-mono text-xs" style={{ color: "var(--text-tertiary)" }}>—</div>
      <div className="font-mono text-xs" style={{ color: "var(--text-tertiary)" }}>
        {sm.escalations}
      </div>
      <div className="font-mono text-xs" style={{ color: "var(--text-primary)" }}>
        {sm.avg_confidence !== null ? sm.avg_confidence.toFixed(2) : "—"}
      </div>
      <div />
    </div>
  );
}

const PALETTE = [
  "var(--brand-primary)",
  "var(--info-fg)",
  "var(--bronze-500, #a67c52)",
  "var(--warning-fg)",
  "var(--gray-400, #9ca3af)",
  "var(--error-fg)",
];

function DistributionBars({
  intents,
  totalVolume,
}: {
  intents: IntentDetail[];
  totalVolume: number;
}) {
  const { t } = useTranslation();
  // Top 6 intents for distribution
  const top = intents.slice(0, 6);

  return (
    <div className="flex flex-col gap-2">
      <div
        className="text-[11.5px] font-semibold uppercase tracking-wider"
        style={{ color: "var(--text-tertiary)" }}
      >
        {t("monitoring.distribution", "Répartition")}
      </div>
      {top.map((intent, i) => {
        const pct =
          totalVolume > 0
            ? Math.round((intent.volume / totalVolume) * 100)
            : 0;
        return (
          <div key={intent.intent_id} className="flex flex-col gap-1">
            <div className="flex justify-between text-[11.5px]">
              <span
                className="truncate"
                style={{ color: "var(--text-primary)" }}
              >
                {intent.intent_id}
              </span>
              <span
                className="font-mono flex-none"
                style={{ color: "var(--text-tertiary)" }}
              >
                {pct}%
              </span>
            </div>
            <div
              className="h-1.5 rounded-full overflow-hidden"
              style={{ background: "var(--gray-100, #f3f4f6)" }}
            >
              <div
                className="h-full"
                style={{
                  width: `${pct}%`,
                  background: PALETTE[i % PALETTE.length],
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
