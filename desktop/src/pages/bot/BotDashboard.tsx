import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Clock,
  History,
  Lightbulb,
  MessageSquare,
  Plus,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useBotDashboard } from "@/hooks/useBotDashboard";
import type { MisclassifiedTurn, Suggestion } from "@/hooks/useBotDashboard";

export function BotDashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: botId } = useParams<{ id: string }>();
  const {
    metrics,
    misclassified,
    suggestions,
    loading,
    error,
    refresh,
    addTrainingExample,
    retrain,
  } = useBotDashboard(botId);

  const [addingExample, setAddingExample] = useState<string | null>(null);
  const [targetIntent, setTargetIntent] = useState("");
  const [maintenanceEnabled, setMaintenanceEnabled] = useState(false);
  const [releases, setReleases] = useState<Array<Record<string, unknown>>>([]);

  // Load maintenance status and releases
  useEffect(() => {
    if (!botId) return;
    Promise.all([
      fetch(`/api/bot/${botId}/maintenance`).then((r) => r.ok ? r.json() : null),
      fetch(`/api/bot/${botId}/releases`).then((r) => r.ok ? r.json() : []),
    ])
      .then(([maint, rels]) => {
        if (maint) setMaintenanceEnabled(maint.maintenance);
        if (rels) setReleases(rels);
      })
      .catch(() => {});
  }, [botId]);

  const toggleMaintenance = async () => {
    const newState = !maintenanceEnabled;
    try {
      const res = await fetch(`/api/bot/${botId}/maintenance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newState }),
      });
      if (res.ok) setMaintenanceEnabled(newState);
    } catch {}
  };

  const rollback = async (version: number) => {
    try {
      const res = await fetch(`/api/bot/${botId}/rollback/${version}`, {
        method: "POST",
      });
      if (res.ok) {
        refresh();
        // Reload releases
        const rels = await fetch(`/api/bot/${botId}/releases`).then((r) => r.json());
        setReleases(rels);
      }
    } catch {}
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-red-500">{error}</p>
      </div>
    );
  }

  const handleAddExample = async (turn: MisclassifiedTurn) => {
    const intent = targetIntent || turn.classified_intent;
    if (!intent) return;
    await addTrainingExample(intent, turn.user_message);
    setAddingExample(null);
    setTargetIntent("");
    refresh();
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/bot/${botId}/wizard`)}
              className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <ArrowLeft size={16} />
            </button>
            <BarChart3 size={18} className="text-brand-500" />
            <h1 className="text-lg font-semibold">Dashboard</h1>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={refresh}>
              <RefreshCw size={14} />
            </Button>
            <Button size="sm" variant="secondary" onClick={retrain}>
              Ré-entraîner
            </Button>
          </div>
        </div>

        {/* Metrics cards */}
        {metrics && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="Sessions"
              value={metrics.total_sessions}
              icon={<MessageSquare size={14} />}
            />
            <MetricCard
              label="Taux selfcare"
              value={`${(metrics.selfcare_rate * 100).toFixed(1)}%`}
              icon={<TrendingUp size={14} />}
              color={metrics.selfcare_rate >= 0.7 ? "green" : "amber"}
            />
            <MetricCard
              label="Escalades"
              value={metrics.escalated_sessions}
              icon={<AlertTriangle size={14} />}
              color={metrics.escalation_rate > 0.3 ? "red" : "green"}
            />
            <MetricCard
              label="Latence P50"
              value={`${metrics.latency_p50_ms.toFixed(0)}ms`}
              icon={<Clock size={14} />}
            />
          </div>
        )}

        {/* Feedback breakdown */}
        {metrics && (metrics.feedback_positive > 0 || metrics.feedback_negative > 0) && (
          <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold mb-3">Feedback</h3>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 text-green-600">
                <ThumbsUp size={14} />
                <span className="text-sm font-medium">{metrics.feedback_positive}</span>
              </div>
              <div className="flex items-center gap-2 text-red-500">
                <ThumbsDown size={14} />
                <span className="text-sm font-medium">{metrics.feedback_negative}</span>
              </div>
              <div className="flex-1 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full"
                  style={{ width: `${metrics.feedback_rate * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {(metrics.feedback_rate * 100).toFixed(0)}% positif
              </span>
            </div>
          </div>
        )}

        {/* Selfcare by intent */}
        {metrics && Object.keys(metrics.selfcare_by_intent).length > 0 && (
          <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold mb-3">Selfcare par intention</h3>
            <div className="space-y-2">
              {Object.entries(metrics.selfcare_by_intent).map(([intent, rate]) => (
                <div key={intent} className="flex items-center gap-3">
                  <span className="text-xs font-medium w-32 truncate">{intent}</span>
                  <div className="flex-1 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        rate >= 0.7 ? "bg-green-500" : rate >= 0.4 ? "bg-amber-500" : "bg-red-500",
                      )}
                      style={{ width: `${rate * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500 w-12 text-right">
                    {(rate * 100).toFixed(0)}%
                  </span>
                  {metrics.escalation_by_intent[intent] && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400">
                      {metrics.escalation_by_intent[intent]} esc.
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {suggestions.length > 0 && (
          <div className="p-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb size={14} className="text-amber-600" />
              <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                Suggestions d'amélioration
              </h3>
            </div>
            <div className="space-y-2">
              {suggestions.map((sg, idx) => (
                <SuggestionCard key={idx} suggestion={sg} />
              ))}
            </div>
          </div>
        )}

        {/* Misclassified turns */}
        {misclassified.length > 0 && (
          <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold mb-3">
              Retours négatifs ({misclassified.length})
            </h3>
            <div className="space-y-2">
              {misclassified.map((turn) => (
                <div
                  key={turn.turn_id}
                  className="flex items-start gap-3 p-3 rounded border border-gray-100 dark:border-gray-800"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">
                      « {turn.user_message} »
                    </p>
                    <p className="text-[10px] text-gray-400 mt-0.5">
                      Classifié : {turn.classified_intent || "—"}
                      {turn.feedback_comment && ` · "${turn.feedback_comment}"`}
                    </p>
                  </div>
                  {addingExample === turn.turn_id ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        className="w-28 rounded border border-gray-200 dark:border-gray-700 px-2 py-1 text-xs"
                        placeholder="Intent ID"
                        value={targetIntent}
                        onChange={(e) => setTargetIntent(e.target.value)}
                      />
                      <Button
                        size="sm"
                        onClick={() => handleAddExample(turn)}
                      >
                        OK
                      </Button>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setAddingExample(turn.turn_id);
                        setTargetIntent(turn.classified_intent || "");
                      }}
                      className="flex items-center gap-1 px-2 py-1 rounded text-xs text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-900/20"
                    >
                      <Plus size={12} />
                      Ajouter
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent sessions */}
        {metrics && metrics.recent_sessions.length > 0 && (
          <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold mb-3">Sessions récentes</h3>
            <div className="space-y-1">
              {metrics.recent_sessions.map((s) => (
                <div
                  key={s.session_id as string}
                  className="flex items-center justify-between px-3 py-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800/50 text-xs cursor-pointer"
                  onClick={() =>
                    navigate(
                      `/bot/${botId}/dashboard/session/${s.session_id}`,
                    )
                  }
                >
                  <span className="font-mono text-gray-400 w-20 truncate">
                    {(s.session_id as string).slice(0, 8)}
                  </span>
                  <span className="font-medium">{(s.current_intent as string) || "—"}</span>
                  <span
                    className={cn(
                      "px-1.5 py-0.5 rounded-full text-[10px]",
                      s.state === "fin" && "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
                      s.state === "escalade" && "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
                      s.state === "timeout" && "bg-gray-100 text-gray-500 dark:bg-gray-800",
                      !["fin", "escalade", "timeout"].includes(s.state as string) && "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
                    )}
                  >
                    {s.state as string}
                  </span>
                  <span className="text-gray-400">
                    {(s.last_activity_at as string).slice(0, 16).replace("T", " ")}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* PRO-7: Maintenance mode toggle */}
        <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Wrench size={14} className="text-gray-400" />
              <h3 className="text-sm font-semibold">Mode maintenance</h3>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "text-xs font-medium px-2 py-0.5 rounded-full",
                  maintenanceEnabled
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                    : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
                )}
              >
                {maintenanceEnabled ? "En maintenance" : "Opérationnel"}
              </span>
              <Button
                size="sm"
                variant={maintenanceEnabled ? "primary" : "ghost"}
                onClick={toggleMaintenance}
              >
                {maintenanceEnabled ? "Désactiver" : "Activer"}
              </Button>
            </div>
          </div>
        </div>

        {/* PRO-2: Release history */}
        {releases.length > 0 && (
          <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 mb-3">
              <History size={14} className="text-gray-400" />
              <h3 className="text-sm font-semibold">Historique des releases</h3>
            </div>
            <div className="space-y-1">
              {releases.map((rel) => (
                <div
                  key={rel.version as number}
                  className="flex items-center justify-between px-3 py-2 rounded text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <span className="font-mono font-medium">v{rel.version as number}</span>
                  <span className="text-gray-400">
                    {(rel.created_at as string).slice(0, 16).replace("T", " ")}
                  </span>
                  <span className="font-mono text-[10px] text-gray-400 w-16 truncate">
                    {(rel.config_hash as string).slice(0, 8)}
                  </span>
                  {rel.active ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      active
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => rollback(rel.version as number)}
                    >
                      Restaurer
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  icon,
  color = "default",
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color?: "default" | "green" | "amber" | "red";
}) {
  const colors = {
    default: "text-gray-700 dark:text-gray-300",
    green: "text-green-600 dark:text-green-400",
    amber: "text-amber-600 dark:text-amber-400",
    red: "text-red-600 dark:text-red-400",
  };

  return (
    <div className="p-3 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-1">
        {icon}
        {label}
      </div>
      <p className={cn("text-lg font-semibold", colors[color])}>
        {value}
      </p>
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const iconMap: Record<string, React.ReactNode> = {
    intent_split: <AlertTriangle size={12} />,
    more_examples: <Plus size={12} />,
  };

  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-amber-600 mt-0.5">
        {iconMap[suggestion.type] || <Lightbulb size={12} />}
      </span>
      <p className="text-amber-800 dark:text-amber-300">{suggestion.message}</p>
    </div>
  );
}
