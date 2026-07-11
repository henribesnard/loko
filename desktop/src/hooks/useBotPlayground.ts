/**
 * LOKO - Hook for the bot playground (session + SSE messaging + traces).
 */
import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  SessionCreateResponse,
  SSEEvent,
  TraceEvent,
  Turn,
} from "@/types/bot";

interface PlaygroundState {
  sessionId: string | null;
  turns: Turn[];
  traces: TraceEvent[];
  streaming: boolean;
  state: string;
  apiKey: string | null;
}

function readApiKey(botId: string | undefined): string | null {
  if (!botId) return null;
  return sessionStorage.getItem(`loko_api_key_${botId}`);
}

function authHeaders(apiKey: string): Record<string, string> {
  return { Authorization: `Bearer ${apiKey}` };
}

function parseSSEBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
    }
  }

  if (!dataLines.length) return null;

  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

function makeBotTurn(content: string, buttons?: string[], sources?: Array<Record<string, unknown>>): Turn {
  return {
    turn_id: crypto.randomUUID(),
    role: "bot",
    content,
    timestamp: new Date().toISOString(),
    buttons,
    sources,
  };
}

interface PendingGeneration {
  text: string;
  sources?: Array<Record<string, unknown>>;
}

export function useBotPlayground(botId: string | undefined) {
  const [playground, setPlayground] = useState<PlaygroundState>({
    sessionId: null,
    turns: [],
    traces: [],
    streaming: false,
    state: "",
    apiKey: readApiKey(botId),
  });
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const createSession = useCallback(async () => {
    if (!botId) return;
    setError(null);

    const apiKey = readApiKey(botId);
    if (!apiKey) {
      setError("Aucune cle API runtime. Generez une cle dans l'etape Publication.");
      return;
    }

    try {
      const data = await api<SessionCreateResponse>(
        `/api/v1/bot/${botId}/sessions`,
        { method: "POST", headers: authHeaders(apiKey) },
      );

      const welcomeTurns: Turn[] = [];
      let state = data.state;
      for (const evt of data.events as SSEEvent[]) {
        if (evt.event === "state" && typeof evt.data.state === "string") {
          state = evt.data.state;
        }
        if (evt.event === "template") {
          welcomeTurns.push(
            makeBotTurn(
              String(evt.data.content || ""),
              evt.data.buttons as string[] | undefined,
            ),
          );
        }
      }

      setPlayground({
        sessionId: data.session_id,
        turns: welcomeTurns,
        traces: [],
        streaming: false,
        state,
        apiKey,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    }
  }, [botId]);

  const sendMessage = useCallback(
    async (text: string, type: "text" | "button_click" = "text") => {
      const sid = playground.sessionId;
      if (!botId || !sid) return;

      const apiKey = playground.apiKey || readApiKey(botId);
      if (!apiKey) {
        setError("Aucune cle API runtime. Generez une cle dans l'etape Publication.");
        return;
      }

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
            headers: {
              "Content-Type": "application/json",
              ...authHeaders(apiKey),
            },
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
        let currentState = playground.state;
        const newBotTurns: Turn[] = [];
        const newTraces: TraceEvent[] = [];
        let pendingGeneration: PendingGeneration = { text: "" };

        const flushGeneration = () => {
          if (!pendingGeneration.text && !pendingGeneration.sources?.length) return;
          newBotTurns.push(makeBotTurn(
            pendingGeneration.text,
            undefined,
            pendingGeneration.sources,
          ));
          pendingGeneration = { text: "" };
        };

        const handleEvent = (event: string, data: Record<string, unknown>) => {
          if (event === "state" && typeof data.state === "string") {
            currentState = data.state;
            return;
          }

          if (event === "generation_delta") {
            pendingGeneration.text += String(data.token || "");
            return;
          }

          if (event === "sources") {
            pendingGeneration.sources = data.sources as Array<Record<string, unknown>>;
            return;
          }

          if (event === "template") {
            flushGeneration();
            newBotTurns.push(
              makeBotTurn(
                String(data.content || ""),
                data.buttons as string[] | undefined,
              ),
            );
            return;
          }

          if (event === "traces") {
            const traces = data.traces as TraceEvent[] | undefined;
            if (traces?.length) newTraces.push(...traces);
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() || "";

          for (const block of blocks) {
            const parsed = parseSSEBlock(block);
            if (parsed) handleEvent(parsed.event, parsed.data);
          }
        }

        if (buffer.trim()) {
          const parsed = parseSSEBlock(buffer);
          if (parsed) handleEvent(parsed.event, parsed.data);
        }

        flushGeneration();

        setPlayground((prev) => ({
          ...prev,
          turns: [...prev.turns, ...newBotTurns],
          traces: [...prev.traces, ...newTraces],
          streaming: false,
          state: currentState,
          apiKey,
        }));
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError(err instanceof Error ? err.message : "Failed to send message");
        }
        setPlayground((prev) => ({ ...prev, streaming: false }));
      }
    },
    [botId, playground.apiKey, playground.sessionId, playground.state],
  );

  const fetchTraces = useCallback(async () => {
    return playground.traces;
  }, [playground.traces]);

  const sendFeedback = useCallback(
    async (turnId: string, rating: "positive" | "negative") => {
      const sid = playground.sessionId;
      if (!botId || !sid) return;
      const apiKey = playground.apiKey || readApiKey(botId);
      if (!apiKey) return;

      await api(`/api/v1/bot/${botId}/sessions/${sid}/feedback`, {
        method: "POST",
        headers: authHeaders(apiKey),
        body: JSON.stringify({ turn_id: turnId, rating }),
      });
    },
    [botId, playground.apiKey, playground.sessionId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setPlayground({
      sessionId: null,
      turns: [],
      traces: [],
      streaming: false,
      state: "",
      apiKey: readApiKey(botId),
    });
    setError(null);
  }, [botId]);

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
