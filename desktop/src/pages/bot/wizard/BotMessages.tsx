import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { api } from "@/lib/api";
import type { WizardStepProps } from "../BotWizard";
import type { MessageTemplate } from "@/types/bot";
import { BotGuardrails } from "./BotGuardrails";

const TEMPLATE_LABEL: Record<string, string> = {
  presentation: "Présentation",
  clarification_inter: "Clarification inter-intentions",
  clarification_intra: "Clarification intra-intention",
  hors_perimetre: "Hors périmètre",
  enquete_satisfaction: "Enquête satisfaction",
  autre_demande: "Autre demande ?",
  fin: "Fin de conversation",
  mise_en_relation: "Mise en relation",
  timeout: "Timeout",
  avant_derniere_demande: "Avant-dernière demande",
  cloture_douce: "Clôture douce",
  demande_inappropriee: "Demande inappropriée",
  fin_ferme: "Clôture ferme",
  maintenance: "Maintenance",
};

interface DefaultsResponse {
  tone: string;
  templates: Record<string, MessageTemplate>;
}

export function BotMessages({ botId, config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();

  // Defaults fetched from server
  const [defaults, setDefaults] = useState<Record<string, MessageTemplate> | null>(null);
  const [defaultsError, setDefaultsError] = useState(false);
  const [tone, setTone] = useState<string>("");

  // Overrides: only user-customized templates
  const [overrides, setOverrides] = useState<Record<string, MessageTemplate>>(
    () => ({ ...config.templates }),
  );

  // Template keys from server defaults (or fallback to override keys)
  const templateKeys = defaults ? Object.keys(defaults) : Object.keys(overrides);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Track focused field for variable insertion
  const [focusedField, setFocusedField] = useState<"text_fr" | "text_en">("text_fr");
  const frRef = useRef<HTMLTextAreaElement>(null);
  const enRef = useRef<HTMLTextAreaElement>(null);

  // Fetch defaults on mount and when tone changes
  useEffect(() => {
    api<DefaultsResponse>(`/api/bot/${botId}/templates/defaults`)
      .then((data) => {
        setDefaults(data.templates);
        setTone(data.tone);
        setDefaultsError(false);
        if (!selectedKey && Object.keys(data.templates).length > 0) {
          setSelectedKey(Object.keys(data.templates)[0]);
        }
      })
      .catch(() => {
        setDefaultsError(true);
      });
  }, [botId, config.tone_profile]); // eslint-disable-line react-hooks/exhaustive-deps

  // Set initial selected key from overrides if defaults not loaded yet
  useEffect(() => {
    if (!selectedKey && templateKeys.length > 0) {
      setSelectedKey(templateKeys[0]);
    }
  }, [templateKeys.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Computed: displayed template = override ?? default
  const defaultTpl = defaults?.[selectedKey];
  const overrideTpl = overrides[selectedKey];
  const current: MessageTemplate = overrideTpl ?? defaultTpl ?? {
    key: selectedKey,
    text_fr: "",
    text_en: "",
    variables: [],
  };
  const isCustom = selectedKey in overrides;

  // Variables available for the current template
  const currentVariables = current.variables ?? defaultTpl?.variables ?? [];

  const updateTemplate = useCallback(
    (field: "text_fr" | "text_en", value: string) => {
      const base = overrides[selectedKey] ?? defaults?.[selectedKey] ?? {
        key: selectedKey,
        text_fr: "",
        text_en: "",
        variables: defaults?.[selectedKey]?.variables ?? [],
      };
      const updated: MessageTemplate = { ...base, [field]: value };

      // Auto-reset: if text matches default exactly, remove override
      if (
        defaults?.[selectedKey] &&
        updated.text_fr === defaults[selectedKey].text_fr &&
        updated.text_en === defaults[selectedKey].text_en
      ) {
        setOverrides((prev) => {
          const next = { ...prev };
          delete next[selectedKey];
          return next;
        });
      } else {
        setOverrides((prev) => ({ ...prev, [selectedKey]: updated }));
      }
      setDirty(true);
      setSaveError(null);
    },
    [selectedKey, overrides, defaults],
  );

  const handleSave = async () => {
    try {
      setSaveError(null);
      await updateConfig({ templates: overrides });
      setDirty(false);
    } catch (e: unknown) {
      const msg =
        e instanceof Error ? e.message : String(e);
      setSaveError(msg);
    }
  };

  const handleReset = () => {
    setOverrides((prev) => {
      const next = { ...prev };
      delete next[selectedKey];
      return next;
    });
    setDirty(true);
    setSaveError(null);
  };

  const insertVariable = (variable: string) => {
    const tag = `{${variable}}`;
    const target = focusedField === "text_en" ? enRef.current : frRef.current;
    if (!target) {
      updateTemplate(focusedField, (current[focusedField] || "") + tag);
      return;
    }
    const start = target.selectionStart ?? target.value.length;
    const end = target.selectionEnd ?? start;
    const before = target.value.slice(0, start);
    const after = target.value.slice(end);
    updateTemplate(focusedField, before + tag + after);
    // Restore cursor position after React re-render
    requestAnimationFrame(() => {
      const newPos = start + tag.length;
      target.selectionStart = newPos;
      target.selectionEnd = newPos;
      target.focus();
    });
  };

  // Preview: safe variable interpolation (all occurrences)
  const preview = (text: string) => {
    const vars: Record<string, string> = {
      nom_bot: config.name,
      intentions_gerees: config.intents.map((i) => i.label).join(", "),
      temps_attente: "~4 min",
      lien_escalade: "#",
      options: "...",
      resume_demandes: "Demande 1, Demande 2",
    };
    return text.replace(/\{(\w+)\}/g, (match, key) => vars[key] ?? match);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">{t("bot.messages.title")}</h3>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowPreview(!showPreview)}
        >
          <Eye size={14} />
          {t("bot.messages.preview")}
        </Button>
      </div>

      {/* Defaults unavailable warning */}
      {defaultsError && (
        <div className="px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 text-xs">
          {t("bot.messages.defaultsUnavailable")}
        </div>
      )}

      {/* Template selector with status badges */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {templateKeys.map((key) => {
            const isModified = key in overrides;
            return (
              <button
                key={key}
                onClick={() => setSelectedKey(key)}
                className={cn(
                  "px-2.5 py-1 rounded-full text-xs font-medium transition-colors inline-flex items-center gap-1",
                  selectedKey === key
                    ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                    : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700",
                )}
              >
                {TEMPLATE_LABEL[key] || key}
                <span
                  className={cn(
                    "inline-block w-1.5 h-1.5 rounded-full",
                    isModified ? "bg-amber-500" : "bg-emerald-500",
                  )}
                />
              </button>
            );
          })}
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-[10px] text-gray-400">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {t("bot.messages.statusDefault")}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {t("bot.messages.statusCustom")}
          </span>
        </div>
      </div>

      {/* Editor panel */}
      {selectedKey && (
        <div className="space-y-4">
          {/* Status badge + reset button */}
          <div className="flex items-center justify-between">
            <span
              className={cn(
                "px-2 py-0.5 rounded text-[11px] font-medium",
                isCustom
                  ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
              )}
            >
              {isCustom
                ? t("bot.messages.statusCustom")
                : `${t("bot.messages.statusDefault")}${tone ? ` — ${tone}` : ""}`}
            </span>
            {isCustom && (
              <Button size="sm" variant="ghost" onClick={handleReset}>
                <RotateCcw size={14} />
                {t("bot.messages.resetDefault")}
              </Button>
            )}
          </div>

          {/* French */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
              Français
            </label>
            <textarea
              ref={frRef}
              value={current.text_fr}
              onChange={(e) => updateTemplate("text_fr", e.target.value)}
              onFocus={() => setFocusedField("text_fr")}
              rows={4}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
            />
          </div>

          {/* English */}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
              English
            </label>
            <textarea
              ref={enRef}
              value={current.text_en}
              onChange={(e) => updateTemplate("text_en", e.target.value)}
              onFocus={() => setFocusedField("text_en")}
              rows={4}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
            />
          </div>

          {/* Variables (filtered by current template) */}
          {currentVariables.length > 0 && (
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                {t("bot.messages.variables")}
              </label>
              <div className="flex flex-wrap gap-1.5">
                {currentVariables.map((v) => (
                  <button
                    key={v}
                    onClick={() => insertVariable(v)}
                    className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 text-xs font-mono text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    {`{${v}}`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Preview (FR + EN) */}
          {showPreview && (current.text_fr || current.text_en) && (
            <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 space-y-3">
              <p className="text-xs font-medium text-gray-500">{t("bot.messages.preview")}</p>
              {current.text_fr && (
                <div>
                  <span className="text-[10px] uppercase text-gray-400 font-semibold">FR</span>
                  <div className="text-sm whitespace-pre-wrap">{preview(current.text_fr)}</div>
                </div>
              )}
              {current.text_en && (
                <div>
                  <span className="text-[10px] uppercase text-gray-400 font-semibold">EN</span>
                  <div className="text-sm whitespace-pre-wrap">{preview(current.text_en)}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Save error */}
      {saveError && (
        <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-xs">
          {saveError}
        </div>
      )}

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}

      {/* Guardrails configuration (GF lot) */}
      <BotGuardrails
        botId={botId}
        onSave={updateConfig}
        saving={saving}
      />
    </div>
  );
}
