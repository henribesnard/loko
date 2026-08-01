/**
 * LOKO — Hook for bot monitoring analytics data.
 *
 * Manages period, comparison, granularity, sort, drill-down state.
 * Parallel fetches on overview, timeseries, funnel, intents.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Period = "7d" | "30d" | "90d";
export type Granularity = "hour" | "day";
export type SortColumn =
  | "intent_id"
  | "volume"
  | "selfcare_rate"
  | "clarifications"
  | "escalations"
  | "avg_confidence"
  | "trend";
export type SortDir = "asc" | "desc";
export type ExportView = "overview" | "intents" | "sub_motifs";

export interface KPIOverview {
  sessions: number;
  messages: number;
  classifications: number;
  answers: number;
  escalations: number;
  escalation_rate: number;
  selfcare_rate: number;
  feedback_up: number;
  feedback_down: number;
  satisfaction_rate: number;
  errors: number;
  error_rate: number;
  guardrail_blocks: number;
  surveys_shown: number;
  surveys_answered: number;
  avg_turns: number;
}

export interface TimeseriesBucket {
  bucket: string;
  sessions: number;
  messages: number;
  escalations: number;
  feedback_up: number;
  feedback_down: number;
  errors: number;
  answers: number;
}

export interface FunnelStep {
  step: string;
  count: number;
  rate: number;
}

export interface IntentDetail {
  intent_id: string;
  volume: number;
  selfcare_rate: number;
  clarifications: number;
  escalations: number;
  avg_confidence: number | null;
  avg_margin: number | null;
  trend: number;
  prev_volume: number;
}

export interface SubMotif {
  sub_motif_id: string;
  volume: number;
  escalations: number;
  selfcare_rate: number;
  avg_confidence: number | null;
}

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

function periodToDays(period: Period): number {
  return period === "7d" ? 7 : period === "30d" ? 30 : 90;
}

function dateRange(period: Period): { from: string; to: string } {
  const now = new Date();
  const to = new Date(now);
  to.setDate(to.getDate() + 1);
  const from = new Date(now);
  from.setDate(from.getDate() - periodToDays(period));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

function prevDateRange(period: Period): { from: string; to: string } {
  const days = periodToDays(period);
  const now = new Date();
  const to = new Date(now);
  to.setDate(to.getDate() - days);
  const from = new Date(to);
  from.setDate(from.getDate() - days);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBotMonitoring(botId: string | undefined) {
  // Controls
  const [period, setPeriod] = useState<Period>("30d");
  const [compare, setCompare] = useState(true);
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [sortColumn, setSortColumn] = useState<SortColumn>("volume");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [drilledIntent, setDrilledIntent] = useState<string | null>(null);

  // Data
  const [overview, setOverview] = useState<KPIOverview | null>(null);
  const [prevOverview, setPrevOverview] = useState<KPIOverview | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesBucket[]>([]);
  const [prevTimeseries, setPrevTimeseries] = useState<TimeseriesBucket[]>([]);
  const [funnel, setFunnel] = useState<FunnelStep[]>([]);
  const [intents, setIntents] = useState<IntentDetail[]>([]);
  const [subMotifs, setSubMotifs] = useState<SubMotif[]>([]);

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { from, to } = useMemo(() => dateRange(period), [period]);
  const prev = useMemo(() => prevDateRange(period), [period]);

  const refresh = useCallback(async () => {
    if (!botId) return;
    setLoading(true);
    setError(null);
    try {
      const qs = `from=${from}&to=${to}`;
      const prevQs = `from=${prev.from}&to=${prev.to}`;

      const requests: Promise<unknown>[] = [
        api<KPIOverview>(`/api/bot/${botId}/analytics/overview?${qs}`),
        api<TimeseriesBucket[]>(
          `/api/bot/${botId}/analytics/kpi/timeseries?${qs}&granularity=${granularity}`,
        ),
        api<FunnelStep[]>(`/api/bot/${botId}/analytics/funnel?${qs}`),
        api<IntentDetail[]>(`/api/bot/${botId}/analytics/intents/detail?${qs}`),
      ];

      // Comparison period data
      if (compare) {
        requests.push(
          api<KPIOverview>(`/api/bot/${botId}/analytics/overview?${prevQs}`),
          api<TimeseriesBucket[]>(
            `/api/bot/${botId}/analytics/kpi/timeseries?${prevQs}&granularity=${granularity}`,
          ),
        );
      }

      const results = await Promise.all(requests);
      setOverview(results[0] as KPIOverview);
      setTimeseries(results[1] as TimeseriesBucket[]);
      setFunnel(results[2] as FunnelStep[]);
      setIntents(results[3] as IntentDetail[]);

      if (compare && results.length > 4) {
        setPrevOverview(results[4] as KPIOverview);
        setPrevTimeseries(results[5] as TimeseriesBucket[]);
      } else {
        setPrevOverview(null);
        setPrevTimeseries([]);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load monitoring data",
      );
    } finally {
      setLoading(false);
    }
  }, [botId, from, to, prev.from, prev.to, granularity, compare]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Drill-down into sub-motifs
  const drillDown = useCallback(
    async (intentId: string) => {
      if (!botId) return;
      setDrilledIntent(intentId);
      try {
        const qs = `from=${from}&to=${to}`;
        const data = await api<SubMotif[]>(
          `/api/bot/${botId}/analytics/intents/${encodeURIComponent(intentId)}/sub-motifs?${qs}`,
        );
        setSubMotifs(data);
      } catch {
        setSubMotifs([]);
      }
    },
    [botId, from, to],
  );

  const drillUp = useCallback(() => {
    setDrilledIntent(null);
    setSubMotifs([]);
  }, []);

  // Sort handler
  const toggleSort = useCallback(
    (col: SortColumn) => {
      if (sortColumn === col) {
        setSortDir((d) => (d === "desc" ? "asc" : "desc"));
      } else {
        setSortColumn(col);
        setSortDir("desc");
      }
    },
    [sortColumn],
  );

  // Sorted intents
  const sortedIntents = useMemo(() => {
    const data = [...intents];
    data.sort((a, b) => {
      const dir = sortDir === "desc" ? -1 : 1;
      if (sortColumn === "intent_id")
        return a.intent_id.localeCompare(b.intent_id) * dir;
      const av = a[sortColumn] ?? 0;
      const bv = b[sortColumn] ?? 0;
      return ((av as number) - (bv as number)) * dir;
    });
    return data;
  }, [intents, sortColumn, sortDir]);

  // CSV export
  const exportCSV = useCallback(
    async (view: ExportView) => {
      if (!botId) return;
      const qs = `from=${from}&to=${to}&view=${view}`;
      const res = await fetch(
        `/api/bot/${botId}/analytics/export?${qs}`,
        { credentials: "include" },
      );
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `loko-analytics-${view}-${from}-${to}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    },
    [botId, from, to],
  );

  // Total volume for share computation
  const totalVolume = useMemo(
    () => intents.reduce((sum, i) => sum + i.volume, 0),
    [intents],
  );

  const isEmpty = !loading && !error && overview !== null && overview.sessions === 0;

  return {
    // Controls
    period,
    setPeriod,
    compare,
    setCompare,
    granularity,
    setGranularity,
    sortColumn,
    sortDir,
    toggleSort,
    drilledIntent,
    drillDown,
    drillUp,

    // Data
    overview,
    prevOverview,
    timeseries,
    prevTimeseries,
    funnel,
    intents: sortedIntents,
    subMotifs,
    totalVolume,

    // State
    loading,
    error,
    isEmpty,
    refresh,
    exportCSV,
  };
}
