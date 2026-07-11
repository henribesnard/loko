import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Clock,
  MessageSquare,
  RefreshCw,
  Send,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useBotPlayground } from "@/hooks/useBotPlayground";
import type { TraceEvent, Turn } from "@/types/bot";

export function BotPlayground() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: botId } = useParams<{ id: string }>();
  const {
    sessionId,
    turns,
    traces,
    streaming,
    state,
    error,
    createSession,
    sendMessage,
    sendFeedback,
    reset,
  } = useBotPlayground(botId);

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-create session on mount
  useEffect(() => {
    if (!sessionId && botId) {
      createSession();
    }
  }, [botId, sessionId, createSession]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    sendMessage(text);
  };

  const handleButtonClick = (text: string) => {
    if (streaming) return;
    sendMessage(text, "button_click");
  };

  const handleReset = () => {
    reset();
    createSession();
  };

  return (
    <div className="flex h-full">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col border-r border-gray-200 dark:border-gray-800">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-800">
          <button
            onClick={() => navigate(`/bot/${botId}/wizard`)}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft size={16} />
          </button>
          <MessageSquare size={16} className="text-brand-500" />
          <h2 className="text-sm font-semibold">{t("bot.playground.title")}</h2>
          <div className="ml-auto flex items-center gap-2">
            {state && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 font-mono">
                {state}
              </span>
            )}
            <Button size="sm" variant="ghost" onClick={handleReset}>
              <RefreshCw size={14} />
            </Button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {turns.map((turn) => (
            <MessageBubble
              key={turn.turn_id}
              turn={turn}
              onButtonClick={handleButtonClick}
              onFeedback={(rating) => sendFeedback(turn.turn_id, rating)}
            />
          ))}

          {streaming && (
            <div className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-400">
              <span className="animate-pulse">●</span>
              <span className="animate-pulse" style={{ animationDelay: "150ms" }}>●</span>
              <span className="animate-pulse" style={{ animationDelay: "300ms" }}>●</span>
            </div>
          )}

          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-xs text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-800">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="Votre message…"
              disabled={streaming || state === "fin" || state === "timeout"}
              className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:opacity-50"
            />
            <Button
              size="sm"
              onClick={handleSend}
              disabled={streaming || !input.trim()}
            >
              <Send size={14} />
            </Button>
          </div>
        </div>
      </div>

      {/* Trace panel */}
      <div className="w-80 flex flex-col bg-gray-50 dark:bg-gray-900/50">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800">
          <h3 className="text-xs font-semibold text-gray-500">
            {t("bot.playground.trace")}
          </h3>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {traces.length === 0 ? (
            <p className="text-xs text-gray-400 text-center mt-8">
              {t("bot.playground.noTrace")}
            </p>
          ) : (
            <div className="space-y-2">
              {traces.map((trace, idx) => (
                <TraceCard key={idx} trace={trace} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MessageBubble({
  turn,
  onButtonClick,
  onFeedback,
}: {
  turn: Turn;
  onButtonClick: (text: string) => void;
  onFeedback: (rating: "positive" | "negative") => void;
}) {
  const isUser = turn.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-3 py-2 text-sm",
          isUser
            ? "bg-brand-500 text-white"
            : "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700",
        )}
      >
        <p className="whitespace-pre-wrap">{turn.content}</p>

        {/* Choice buttons */}
        {turn.buttons && turn.buttons.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {turn.buttons.map((btn) => (
              <button
                key={btn}
                onClick={() => onButtonClick(btn)}
                className="px-2.5 py-1 rounded-full border border-brand-200 dark:border-brand-700 text-xs text-brand-700 dark:text-brand-300 hover:bg-brand-50 dark:hover:bg-brand-900/30 transition-colors"
              >
                {btn}
              </button>
            ))}
          </div>
        )}

        {turn.sources && turn.sources.length > 0 && (
          <div className="mt-2 space-y-1 text-[11px] opacity-80">
            {turn.sources.map((source, idx) => {
              const url = String(source.url || source.source_url || "");
              const title = String(source.title || source.source_title || url || `Source ${idx + 1}`);
              return url ? (
                <a
                  key={`${url}-${idx}`}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="block underline"
                >
                  {title}
                </a>
              ) : (
                <span key={idx} className="block">{title}</span>
              );
            })}
          </div>
        )}

        {/* Feedback (bot messages only) */}
        {!isUser && (
          <div className="mt-1.5 flex items-center gap-1">
            <button
              onClick={() => onFeedback("positive")}
              className="p-1 rounded text-gray-300 hover:text-green-500 transition-colors"
            >
              <ThumbsUp size={12} />
            </button>
            <button
              onClick={() => onFeedback("negative")}
              className="p-1 rounded text-gray-300 hover:text-red-500 transition-colors"
            >
              <ThumbsDown size={12} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function TraceCard({ trace }: { trace: TraceEvent }) {
  const [expanded, setExpanded] = useState(false);

  const stepLabel: Record<string, string> = {
    classification_l1: "Classification L1",
    classification_l2: "Classification L2",
    retrieval: "Retrieval",
    generation: "Génération",
    template: "Template",
    escalation: "Escalade",
  };

  const stepColor: Record<string, string> = {
    classification_l1: "text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400",
    classification_l2: "text-indigo-600 bg-indigo-50 dark:bg-indigo-900/30 dark:text-indigo-400",
    retrieval: "text-amber-600 bg-amber-50 dark:bg-amber-900/30 dark:text-amber-400",
    generation: "text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400",
    template: "text-gray-600 bg-gray-100 dark:bg-gray-800 dark:text-gray-400",
    escalation: "text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400",
  };

  return (
    <div
      className="rounded border border-gray-200 dark:border-gray-700 overflow-hidden cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center justify-between px-2.5 py-1.5">
        <span
          className={cn(
            "text-[10px] font-medium px-1.5 py-0.5 rounded",
            stepColor[trace.step] || "text-gray-500 bg-gray-100",
          )}
        >
          {stepLabel[trace.step] || trace.step}
        </span>
        <span className="flex items-center gap-1 text-[10px] text-gray-400">
          <Clock size={10} />
          {trace.latency_ms.toFixed(0)}ms
        </span>
      </div>
      {expanded && Object.keys(trace.detail).length > 0 && (
        <div className="px-2.5 pb-2 border-t border-gray-100 dark:border-gray-800">
          <pre className="text-[10px] text-gray-500 whitespace-pre-wrap mt-1.5 max-h-40 overflow-y-auto">
            {JSON.stringify(trace.detail, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
