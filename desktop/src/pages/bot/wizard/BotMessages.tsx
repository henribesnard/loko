import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import type { WizardStepProps } from "../BotWizard";
import type { MessageTemplate } from "@/types/bot";
import { TEMPLATE_KEYS, TEMPLATE_VARIABLES } from "@/types/bot";
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
  // ORC/GF/PRO new templates
  avant_derniere_demande: "Avant-dernière demande",
  cloture_douce: "Clôture douce",
  demande_inappropriee: "Demande inappropriée",
  fin_ferme: "Clôture ferme",
  maintenance: "Maintenance",
};

export function BotMessages({ botId, config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [selectedKey, setSelectedKey] = useState<string>(TEMPLATE_KEYS[0]);
  const [templates, setTemplates] = useState<Record<string, MessageTemplate>>(
    { ...config.templates },
  );
  const [dirty, setDirty] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const current = templates[selectedKey] || {
    key: selectedKey,
    text_fr: "",
    text_en: "",
    variables: [],
  };

  const updateTemplate = (field: "text_fr" | "text_en", value: string) => {
    const updated = { ...current, [field]: value };
    setTemplates((prev) => ({ ...prev, [selectedKey]: updated }));
    setDirty(true);
  };

  const handleSave = async () => {
    await updateConfig({ templates });
    setDirty(false);
  };

  const insertVariable = (variable: string, field: "text_fr" | "text_en") => {
    const tag = `{${variable}}`;
    updateTemplate(field, (current[field] || "") + tag);
  };

  // Preview: simple variable interpolation
  const preview = (text: string) => {
    return text
      .replace("{nom_bot}", config.name)
      .replace("{intentions_gerees}", config.intents.map((i) => i.label).join(", "))
      .replace("{temps_attente}", "~4 min")
      .replace("{lien_escalade}", "#")
      .replace("{options}", "...")
      .replace("{resume_demandes}", "Demande 1, Demande 2");
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

      {/* Template selector */}
      <div className="flex flex-wrap gap-1.5">
        {TEMPLATE_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => setSelectedKey(key)}
            className={cn(
              "px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
              selectedKey === key
                ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700",
            )}
          >
            {TEMPLATE_LABEL[key] || key}
          </button>
        ))}
      </div>

      {/* Editor */}
      <div className="grid grid-cols-1 gap-4">
        {/* French */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
            Français
          </label>
          <textarea
            value={current.text_fr}
            onChange={(e) => updateTemplate("text_fr", e.target.value)}
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
            value={current.text_en}
            onChange={(e) => updateTemplate("text_en", e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
          />
        </div>
      </div>

      {/* Variables */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.messages.variables")}
        </label>
        <div className="flex flex-wrap gap-1.5">
          {TEMPLATE_VARIABLES.map((v) => (
            <button
              key={v}
              onClick={() => insertVariable(v, "text_fr")}
              className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 text-xs font-mono text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              {`{${v}}`}
            </button>
          ))}
        </div>
      </div>

      {/* Preview */}
      {showPreview && current.text_fr && (
        <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
          <p className="text-xs font-medium text-gray-500 mb-2">{t("bot.messages.preview")}</p>
          <div className="text-sm whitespace-pre-wrap">{preview(current.text_fr)}</div>
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
