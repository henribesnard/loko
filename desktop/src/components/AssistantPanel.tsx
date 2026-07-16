import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Loader2,
  Sparkles,
  X,
  AlertTriangle,
  Search,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useAssistant } from "@/hooks/useAssistant";
import type { Proposal } from "@/types/bot";

type SubMode = "generate" | "discriminate" | "review";

interface AssistantPanelProps {
  botId: string;
  intentId: string;
  intentLabel: string;
  onAccepted: () => void;
  onClose: () => void;
}

export function AssistantPanel({
  botId,
  intentId,
  intentLabel,
  onAccepted,
  onClose,
}: AssistantPanelProps) {
  const { t } = useTranslation();
  const { proposals, loading, error, ask, accept, reject, rejectAll, clear } =
    useAssistant(botId);
  const [subMode, setSubMode] = useState<SubMode>("generate");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const pendingProposals = proposals.filter((p) => p.status === "pending");
  const acceptedProposals = proposals.filter((p) => p.status === "accepted");

  const handleAsk = useCallback(() => {
    clear();
    setSelected(new Set());
    ask({
      use_case: "a2_examples",
      sub_mode: subMode,
      intent_id: intentId,
      context: {},
    });
  }, [ask, clear, subMode, intentId]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllPending = () => {
    setSelected(new Set(pendingProposals.map((p) => p.id)));
  };

  const handleAccept = async () => {
    const items = proposals
      .filter((p) => selected.has(p.id) && p.status === "pending")
      .map((p) => ({ intent_id: p.intent_id, content: p.content }));
    if (items.length === 0) return;
    try {
      await accept(items);
      setSelected(new Set());
      onAccepted();
    } catch {
      // error is set in the hook
    }
  };

  const handleRejectAll = () => {
    rejectAll();
    setSelected(new Set());
  };

  const tabs: { key: SubMode; label: string; icon: typeof Sparkles }[] = [
    { key: "generate", label: t("bot.assistant.generate"), icon: Wand2 },
    { key: "discriminate", label: t("bot.assistant.discriminate"), icon: Search },
    { key: "review", label: t("bot.assistant.review"), icon: AlertTriangle },
  ];

  return (
    <div className="w-80 flex flex-col bg-gray-50 dark:bg-gray-900/50 border-l border-gray-200 dark:border-gray-800">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-brand-500" />
          <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            {t("bot.assistant.title")}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400"
        >
          <X size={14} />
        </button>
      </div>

      {/* Intent context */}
      <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-800">
        <p className="text-[10px] text-gray-400 uppercase tracking-wider">
          Intention
        </p>
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">
          {intentLabel}
        </p>
      </div>

      {/* Sub-mode tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => {
              setSubMode(key);
              clear();
              setSelected(new Set());
            }}
            className={cn(
              "flex-1 px-2 py-2 text-[11px] font-medium flex items-center justify-center gap-1 transition-colors",
              subMode === key
                ? "text-brand-600 dark:text-brand-400 border-b-2 border-brand-500"
                : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300",
            )}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* Action button */}
      <div className="px-4 py-3">
        <Button
          size="sm"
          onClick={handleAsk}
          disabled={loading}
          className="w-full"
        >
          {loading ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              {t("bot.assistant.generating")}
            </>
          ) : (
            <>
              <Sparkles size={14} />
              {tabs.find((tab) => tab.key === subMode)?.label}
            </>
          )}
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 pb-2">
          <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-[11px]">
            {error === "quota_exceeded"
              ? t("bot.assistant.quotaExceeded")
              : error === "llm_unavailable"
                ? t("bot.assistant.llmUnavailable")
                : error}
          </div>
        </div>
      )}

      {/* Proposals list */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1.5">
        {proposals.length === 0 && !loading && (
          <p className="text-xs text-gray-400 text-center mt-4">
            {t("bot.assistant.noProposals")}
          </p>
        )}
        {proposals.map((p) => (
          <ProposalCard
            key={p.id}
            proposal={p}
            selected={selected.has(p.id)}
            onToggle={() => toggleSelect(p.id)}
            onReject={() => reject(p.id)}
          />
        ))}
      </div>

      {/* Footer actions */}
      {pendingProposals.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-800 space-y-2">
          {selected.size < pendingProposals.length && (
            <button
              onClick={selectAllPending}
              className="text-[11px] text-brand-500 hover:text-brand-600"
            >
              {t("bot.assistant.selectAll", {
                count: pendingProposals.length,
              })}
            </button>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleAccept}
              disabled={selected.size === 0}
              className="flex-1"
            >
              <Check size={12} />
              {t("bot.assistant.acceptSelected")} ({selected.size})
            </Button>
            <Button size="sm" variant="ghost" onClick={handleRejectAll}>
              {t("bot.assistant.rejectAll")}
            </Button>
          </div>
        </div>
      )}

      {/* Accepted count */}
      {acceptedProposals.length > 0 && pendingProposals.length === 0 && (
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-800">
          <p className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
            <Check size={12} />
            {t("bot.assistant.accepted", {
              count: acceptedProposals.length,
            })}
          </p>
        </div>
      )}
    </div>
  );
}

function ProposalCard({
  proposal,
  selected,
  onToggle,
  onReject,
}: {
  proposal: Proposal;
  selected: boolean;
  onToggle: () => void;
  onReject: () => void;
}) {
  const { t } = useTranslation();
  const isPending = proposal.status === "pending";
  const isAccepted = proposal.status === "accepted";
  const isRejected = proposal.status === "rejected";

  return (
    <div
      className={cn(
        "p-2 rounded-lg border text-xs transition-all",
        isAccepted &&
          "border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 opacity-70",
        isRejected &&
          "border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 opacity-40 line-through",
        isPending &&
          selected &&
          "border-brand-300 dark:border-brand-700 bg-brand-50 dark:bg-brand-900/20",
        isPending &&
          !selected &&
          "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800",
      )}
    >
      <div className="flex items-start gap-2">
        {isPending && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="mt-0.5 rounded border-gray-300"
          />
        )}
        {isAccepted && (
          <Check size={12} className="mt-0.5 text-green-500 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-gray-800 dark:text-gray-200 break-words">
            {proposal.content}
          </p>
          {proposal.rationale && (
            <p className="mt-1 text-[10px] text-gray-400 italic">
              {proposal.rationale}
            </p>
          )}
        </div>
        {isPending && (
          <button
            onClick={onReject}
            className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-400 shrink-0"
            title={t("bot.assistant.reject")}
          >
            <X size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
