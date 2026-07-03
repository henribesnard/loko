/**
 * LOKO — Hook for bot training and evaluation.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { TrainingStatus, EvaluationResult } from "@/types/bot";

export function useBotTraining(botId: string | undefined) {
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    if (!botId) return;
    try {
      const data = await api<TrainingStatus>(`/api/bot/${botId}/train/status`);
      setStatus(data);
      if (data.status === "completed" || data.status === "failed") {
        stopPolling();
        if (data.status === "completed") {
          fetchEvaluation();
        }
      }
    } catch {
      // Ignore polling errors
    }
  }, [botId, stopPolling]);

  const fetchEvaluation = useCallback(async () => {
    if (!botId) return;
    try {
      const data = await api<EvaluationResult>(`/api/bot/${botId}/evaluation`);
      setEvaluation(data);
    } catch {
      // No evaluation available yet
    }
  }, [botId]);

  const startTraining = useCallback(
    async (baseModel?: string, runEvaluation = true) => {
      if (!botId) return;
      setError(null);
      try {
        await api(`/api/bot/${botId}/train`, {
          method: "POST",
          body: JSON.stringify({
            base_model: baseModel || "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            run_evaluation: runEvaluation,
          }),
        });
        setStatus({ bot_id: botId, status: "running", step: "queued" });

        // Poll for status
        pollRef.current = setInterval(fetchStatus, 2000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Training failed to start");
      }
    },
    [botId, fetchStatus],
  );

  // Fetch initial status + evaluation on mount
  useEffect(() => {
    if (!botId) return;
    fetchStatus();
    fetchEvaluation();
    return stopPolling;
  }, [botId, fetchStatus, fetchEvaluation, stopPolling]);

  const isTraining = status?.status === "running";

  return { status, evaluation, isTraining, error, startTraining, fetchEvaluation };
}
