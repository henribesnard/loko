/**
 * LOKO — Hook for the bot playground (session + SSE messaging + traces).
 */
import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  SessionCreateResponse,
  TraceEvent,
  Turn,
} from "@/types/bot";

interface PlaygroundState {
  sessionId: string | null;
  turns: Turn[];
  traces: TraceEvent[];
  streaming: boolean;
  state: string;
}

export function useBotPlayground(botId: string | undefined) {
  const [playground, setPlayground] = useState<PlaygroundState>({
    sessionId: null,
    turns: [],
    traces: [],
    streaming: false,
    state: "",
  });
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const createSession = useCallback(async () => {
    if (!botId) return;
    setError(null);
    try {
      const data = await api<SessionCreateResponse>(
        `/api/v1/bot/${botId}/sessions`,
        { method: "POST" },
      );

      // Extract turns from welcome events
      const welcomeTurns: Turn[] = [];
      for (const evt of data.events) {
        if (evt.event === "template" || evt.event === "generation_delta") {
          welcomeTurns.push({
            turn_id: (evt.data.turn_id as string) || "",
            role: "bot",
            content: (evt.data.text as string) || "",
            timestamp: new Date().toISOString(),
            buttons: evt.data.buttons as string[] | undefined,
          });
        }
      }

      setPlayground({
        sessionId: data.session_id,
        turns: welcomeTurns,
        traces: [],
        streaming: false,
        state: data.state,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    }
  }, [botId]);

  const sendMessage = useCallback(
    async (text: string, type: "text" | "button_click" = "text") => {
      const sid = playground.sessionId;
      if (!botId || !sid) return;

      // Add user turn
      const userTurn: Turn = {
        turn_id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
        button_selected: type === "button_click" ? text : undefined,
      };

      setPlayground((prev) => ({
        ...prev,
        turns: [...prev.turns, userTurn],
        streaming: true,
      }));

      setError(null);

      try {
        abortRef.current = new AbortController();

        const res = await fetch(
          `/api/v1/bot/${botId}/sessions/${sid}/messages`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, type }),
            signal: abortRef.current.signal,
          },
        );

        if (!res.ok) {
          const body = await res.text();
          throw new Error(`API ${res.status}: ${body}`);
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let currentBotText = "";
        let currentButtons: string[] | undefined;
        let currentState = playground.state;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              continue;
            }
            if (line.startsWith("data: ")) {
              const jsonStr = line.slice(6);
              try {
                const data = JSON.parse(jsonStr);

                if (data.state) {
                  currentState = data.state;
                }

                if (data.text !== undefined) {
                  currentBotText += data.text;
                }

                if (data.buttons) {
                  currentButtons = data.buttons;
                }

                setPlayground((prev) => ({
                  ...prev,
                  state: currentState,
                }));
              } catch {
                // Ignore parse errors for partial lines
              }
            }
          }
        }

        // Add the final bot turn
        if (currentBotText) {
          const botTurn: Turn = {
            turn_id: crypto.randomUUID(),
            role: "bot",
            content: currentBotText,
            timestamp: new Date().toISOString(),
            buttons: currentButtons,
          };

          setPlayground((prev) => ({
            ...prev,
            turns: [...prev.turns, botTurn],
            streaming: false,
            state: currentState,
          }));
        } else {
          setPlayground((prev) => ({
            ...prev,
            streaming: false,
            state: currentState,
          }));
        }

        // Fetch traces
        await fetchTraces(sid);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError(err instanceof Error ? err.message : "Failed to send message");
        }
        setPlayground((prev) => ({ ...prev, streaming: false }));
      }
    },
    [botId, playground.sessionId, playground.state],
  );

  const fetchTraces = useCallback(
    async (sessionId?: string) => {
      const sid = sessionId || playground.sessionId;
      if (!botId || !sid) return;
      try {
        const traces = await api<TraceEvent[]>(
          `/api/v1/bot/${botId}/sessions/${sid}/traces`,
        );
        setPlayground((prev) => ({ ...prev, traces }));
      } catch {
        // Traces are optional
      }
    },
    [botId, playground.sessionId],
  );

  const sendFeedback = useCallback(
    async (turnId: string, rating: "positive" | "negative") => {
      const sid = playground.sessionId;
      if (!botId || !sid) return;
      await api(`/api/v1/bot/${botId}/sessions/${sid}/feedback`, {
        method: "POST",
        body: JSON.stringify({ turn_id: turnId, rating }),
      });
    },
    [botId, playground.sessionId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setPlayground({
      sessionId: null,
      turns: [],
      traces: [],
      streaming: false,
      state: "",
    });
    setError(null);
  }, []);

  return {
    ...playground,
    error,
    createSession,
    sendMessage,
    sendFeedback,
    fetchTraces,
    reset,
  };
}
