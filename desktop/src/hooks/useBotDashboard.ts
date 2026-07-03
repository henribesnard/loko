/**
 * LOKO — Hook for bot dashboard metrics and improvement.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export interface DashboardMetrics {
  total_sessions: number;
  completed_sessions: number;
  escalated_sessions: number;
  timed_out_sessions: number;
  selfcare_rate: number;
  escalation_rate: number;
  clarification_rate: number;
  selfcare_by_intent: Record<string, number>;
  escalation_by_intent: Record<string, number>;
  latency_p50_ms: number;
  latency_p95_ms: number;
  feedback_positive: number;
  feedback_negative: number;
  feedback_rate: number;
  recent_sessions: Array<Record<string, unknown>>;
}

export interface MisclassifiedTurn {
  session_id: string;
  turn_id: string;
  user_message: string;
  classified_intent: string;
  sub_motif: string | null;
  feedback_comment: string;
  feedback_time: string;
  classification_scores: Array<[string, number]>;
}

export interface Suggestion {
  type: string;
  intent_id: string;
  message: string;
  [key: string]: unknown;
}

export function useBotDashboard(botId: string | undefined) {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [misclassified, setMisclassified] = useState<MisclassifiedTurn[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!botId) return;
    setLoading(true);
    setError(null);
    try {
      const [m, mc, sg] = await Promise.all([
        api<DashboardMetrics>(`/api/bot/${botId}/dashboard/metrics`),
        api<MisclassifiedTurn[]>(`/api/bot/${botId}/dashboard/misclassified`),
        api<Suggestion[]>(`/api/bot/${botId}/dashboard/suggestions`),
      ]);
      setMetrics(m);
      setMisclassified(mc);
      setSuggestions(sg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addTrainingExample = useCallback(
    async (intentId: string, text: string) => {
      if (!botId) return;
      await api(`/api/bot/${botId}/dashboard/add-example`, {
        method: "POST",
        body: JSON.stringify({
          intent_id: intentId,
          text,
          from_production: true,
        }),
      });
    },
    [botId],
  );

  const retrain = useCallback(async () => {
    if (!botId) return;
    await api(`/api/bot/${botId}/dashboard/retrain`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  }, [botId]);

  return {
    metrics,
    misclassified,
    suggestions,
    loading,
    error,
    refresh,
    addTrainingExample,
    retrain,
  };
}
