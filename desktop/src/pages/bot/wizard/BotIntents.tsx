import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Download,
  Loader2,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { useBotTraining } from "@/hooks/useBotTraining";
import { exportIntentsToCSV, parseIntentsCSV, downloadCSV } from "@/lib/csv-intents";
import type { WizardStepProps } from "../BotWizard";
import type { Intent, SubMotif } from "@/types/bot";

export function BotIntents({ botId, config, updateConfig }: WizardStepProps) {
  const { t } = useTranslation();
  const { status, evaluation, isTraining, startTraining } = useBotTraining(botId);
  const [expandedIntent, setExpandedIntent] = useState<string | null>(null);
  const [showSubMotifs, setShowSubMotifs] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importStatus, setImportStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const intents = config.intents;

  const updateIntents = (updated: Intent[]) => {
    updateConfig({ intents: updated });
  };

  const addIntent = () => {
    const id = `intent_${Date.now()}`;
    const newIntent: Intent = {
      id,
      label: "",
      definition: "",
      examples: [],
      sub_motifs: [],
      is_system: false,
    };
    updateIntents([...intents, newIntent]);
    setExpandedIntent(id);
  };

  const removeIntent = (intentId: string) => {
    updateIntents(intents.filter((i) => i.id !== intentId));
  };

  const updateIntent = (intentId: string, updates: Partial<Intent>) => {
    updateIntents(
      intents.map((i) => (i.id === intentId ? { ...i, ...updates } : i)),
    );
  };

  const addExample = (intentId: string) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    updateIntent(intentId, { examples: [...intent.examples, ""] });
  };

  const updateExample = (intentId: string, idx: number, value: string) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    const examples = [...intent.examples];
    examples[idx] = value;
    updateIntent(intentId, { examples });
  };

  const removeExample = (intentId: string, idx: number) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    updateIntent(intentId, {
      examples: intent.examples.filter((_, i) => i !== idx),
    });
  };

  const addSubMotif = (intentId: string) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    const sm: SubMotif = {
      id: `sm_${Date.now()}`,
      label: "",
      definition: "",
      examples: ["", "", ""],
    };
    updateIntent(intentId, { sub_motifs: [...intent.sub_motifs, sm] });
  };

  const removeSubMotif = (intentId: string, smId: string) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    updateIntent(intentId, {
      sub_motifs: intent.sub_motifs.filter((s) => s.id !== smId),
    });
  };

  const updateSubMotif = (
    intentId: string,
    smId: string,
    updates: Partial<SubMotif>,
  ) => {
    const intent = intents.find((i) => i.id === intentId);
    if (!intent) return;
    updateIntent(intentId, {
      sub_motifs: intent.sub_motifs.map((s) =>
        s.id === smId ? { ...s, ...updates } : s,
      ),
    });
  };

  // CSV export
  const handleExport = () => {
    const csv = exportIntentsToCSV(intents);
    const date = new Date().toISOString().slice(0, 10);
    downloadCSV(csv, `intents_${date}.csv`);
  };

  // CSV import
  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const csvText = event.target?.result as string;
        const merged = parseIntentsCSV(csvText, intents);
        updateIntents(merged);

        const added = merged.length - intents.length;
        const msg = added > 0
          ? t("bot.intents.importSuccessNew", { count: merged.length, new: added })
          : t("bot.intents.importSuccess", { count: merged.length });
        setImportStatus({ type: "success", message: msg });
      } catch (err) {
        setImportStatus({
          type: "error",
          message: t("bot.intents.importError", {
            detail: err instanceof Error ? err.message : String(err),
          }),
        });
      }
    };
    reader.onerror = () => {
      setImportStatus({
        type: "error",
        message: t("bot.intents.importError", { detail: "Failed to read file" }),
      });
    };
    reader.readAsText(file, "utf-8");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">{t("bot.intents.title")}</h3>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={handleExport}>
            <Download size={14} />
            {t("bot.intents.exportCSV")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => fileInputRef.current?.click()}>
            <Upload size={14} />
            {t("bot.intents.importCSV")}
          </Button>
          <Button size="sm" variant="ghost" onClick={addIntent}>
            <Plus size={14} />
            {t("bot.intents.add")}
          </Button>
          <Button
            size="sm"
            onClick={() => startTraining()}
            disabled={isTraining}
          >
            {isTraining ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                {t("bot.intents.training")}
              </>
            ) : (
              t("bot.intents.train")
            )}
          </Button>
        </div>
      </div>

      {/* Hidden file input for CSV import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={handleFileSelected}
      />

      {/* Import feedback */}
      {importStatus && (
        <div
          className={cn(
            "px-3 py-2 rounded-lg text-xs flex items-center gap-2",
            importStatus.type === "success" &&
              "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300",
            importStatus.type === "error" &&
              "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
          )}
        >
          {importStatus.type === "error" && <AlertCircle size={14} />}
          {importStatus.message}
          <button
            onClick={() => setImportStatus(null)}
            className="ml-auto p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Training status */}
      {status && status.status !== "idle" && (
        <div
          className={cn(
            "px-3 py-2 rounded-lg text-xs",
            status.status === "running" &&
              "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
            status.status === "completed" &&
              "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300",
            status.status === "failed" &&
              "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
          )}
        >
          {status.status === "running" && `${t("bot.intents.training")} — ${status.step}`}
          {status.status === "completed" && t("bot.intents.trained")}
          {status.status === "failed" && `${t("common.error")}: ${status.error}`}
        </div>
      )}

      {/* Evaluation */}
      {evaluation && (
        <div className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium">{t("bot.intents.evaluation")}</span>
            <span className="text-brand-600 dark:text-brand-400 font-semibold">
              {t("bot.intents.accuracy")}: {(evaluation.accuracy * 100).toFixed(1)}%
            </span>
          </div>
          {evaluation.per_class && (
            <div className="space-y-1">
              {Object.entries(evaluation.per_class).map(([cls, metrics]) => (
                <div key={cls} className="flex justify-between text-gray-500">
                  <span>{cls}</span>
                  <span>F1: {(metrics.f1 * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Intents list */}
      <div className="space-y-2">
        {intents.map((intent) => {
          const isExpanded = expandedIntent === intent.id;
          const exampleCount = intent.examples.filter((e) => e.trim()).length;
          const hasEnough = intent.is_system || exampleCount >= 8;

          return (
            <div
              key={intent.id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Intent header */}
              <button
                onClick={() =>
                  setExpandedIntent(isExpanded ? null : intent.id)
                }
                className="w-full flex items-center gap-2 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown size={14} />
                ) : (
                  <ChevronRight size={14} />
                )}
                <span className="text-sm font-medium flex-1 text-left">
                  {intent.label || intent.id}
                </span>
                <span
                  className={cn(
                    "text-xs px-2 py-0.5 rounded-full",
                    hasEnough
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
                  )}
                >
                  {t("bot.intents.examplesCount", { count: exampleCount })}
                </span>
                {intent.is_system && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500">
                    system
                  </span>
                )}
                {!intent.is_system && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeIntent(intent.id);
                    }}
                    className="p-1 rounded text-gray-400 hover:text-red-500"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </button>

              {/* Intent body */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-4 border-t border-gray-100 dark:border-gray-800">
                  <div className="grid grid-cols-2 gap-3 pt-3">
                    <Input
                      label={t("bot.intents.label")}
                      value={intent.label}
                      onChange={(e) =>
                        updateIntent(intent.id, { label: e.target.value })
                      }
                    />
                    <Input
                      label="ID"
                      value={intent.id}
                      onChange={(e) => {
                        const newId = e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9_]/g, "_");
                        // Update the intent with the new ID
                        updateIntents(
                          intents.map((i) =>
                            i.id === intent.id ? { ...i, id: newId } : i,
                          ),
                        );
                        setExpandedIntent(newId);
                      }}
                      disabled={intent.is_system}
                    />
                  </div>

                  <Input
                    label={t("bot.intents.definition")}
                    value={intent.definition}
                    onChange={(e) =>
                      updateIntent(intent.id, { definition: e.target.value })
                    }
                  />

                  {/* Examples */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
                        {t("bot.intents.examples")}
                      </label>
                      {!hasEnough && (
                        <span className="text-xs text-amber-600">
                          {t("bot.intents.minExamples")}
                        </span>
                      )}
                    </div>
                    {intent.examples.map((ex, idx) => (
                      <div key={idx} className="flex gap-1.5">
                        <input
                          className="flex-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                          value={ex}
                          onChange={(e) =>
                            updateExample(intent.id, idx, e.target.value)
                          }
                          placeholder={`Exemple ${idx + 1}`}
                        />
                        <button
                          onClick={() => removeExample(intent.id, idx)}
                          className="p-1 text-gray-400 hover:text-red-500"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => addExample(intent.id)}
                      className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400"
                    >
                      <Plus size={12} />
                      {t("bot.intents.addExample")}
                    </button>
                  </div>

                  {/* Sub-motifs toggle */}
                  <div>
                    <button
                      onClick={() =>
                        setShowSubMotifs(
                          showSubMotifs === intent.id ? null : intent.id,
                        )
                      }
                      className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    >
                      {showSubMotifs === intent.id ? (
                        <ChevronDown size={12} />
                      ) : (
                        <ChevronRight size={12} />
                      )}
                      {t("bot.intents.subMotifs")} ({intent.sub_motifs.length})
                    </button>

                    {showSubMotifs === intent.id && (
                      <div className="mt-2 pl-4 space-y-3 border-l-2 border-gray-100 dark:border-gray-800">
                        {intent.sub_motifs.map((sm) => (
                          <div key={sm.id} className="space-y-2">
                            <div className="flex items-center gap-2">
                              <input
                                className="flex-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                                value={sm.label}
                                onChange={(e) =>
                                  updateSubMotif(intent.id, sm.id, {
                                    label: e.target.value,
                                  })
                                }
                                placeholder="Libellé sous-motif"
                              />
                              <button
                                onClick={() =>
                                  removeSubMotif(intent.id, sm.id)
                                }
                                className="p-1 text-gray-400 hover:text-red-500"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                            {sm.examples.map((ex, idx) => (
                              <input
                                key={idx}
                                className="w-full rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
                                value={ex}
                                onChange={(e) => {
                                  const exs = [...sm.examples];
                                  exs[idx] = e.target.value;
                                  updateSubMotif(intent.id, sm.id, {
                                    examples: exs,
                                  });
                                }}
                                placeholder={`Exemple ${idx + 1}`}
                              />
                            ))}
                          </div>
                        ))}
                        <button
                          onClick={() => addSubMotif(intent.id)}
                          className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400"
                        >
                          <Plus size={12} />
                          {t("bot.intents.addSubMotif")}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
