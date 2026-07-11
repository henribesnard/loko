import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import type { WizardStepProps } from "../BotWizard";
import type { JourneyParams } from "@/types/bot";
import { JOURNEY_DEFAULTS } from "@/types/bot";
import { BotLLM } from "./BotLLM";

// Only numeric keys from JourneyParams (exclude boolean fields)
type NumericJourneyKey = {
  [K in keyof JourneyParams]: JourneyParams[K] extends number ? K : never;
}[keyof JourneyParams];

interface ParamConfig {
  key: NumericJourneyKey;
  labelKey: string;
  min: number;
  max: number;
  step: number;
  isFloat: boolean;
}

const PARAMS: ParamConfig[] = [
  { key: "seuil_haut", labelKey: "bot.journey.seuilHaut", min: 0, max: 1, step: 0.05, isFloat: true },
  { key: "seuil_bas", labelKey: "bot.journey.seuilBas", min: 0, max: 1, step: 0.05, isFloat: true },
  { key: "seuil_sous_motif", labelKey: "bot.journey.seuilSousMotif", min: 0, max: 1, step: 0.05, isFloat: true },
  { key: "max_clarifications", labelKey: "bot.journey.maxClarifications", min: 0, max: 3, step: 1, isFloat: false },
  { key: "max_demandes", labelKey: "bot.journey.maxDemandes", min: 1, max: 20, step: 1, isFloat: false },
  { key: "timeout_inactivite_s", labelKey: "bot.journey.timeoutInactivite", min: 30, max: 3600, step: 30, isFloat: false },
  { key: "retrieval_min_score", labelKey: "bot.journey.retrievalMinScore", min: 0, max: 1, step: 0.05, isFloat: true },
  { key: "retrieval_min_chunks", labelKey: "bot.journey.retrievalMinChunks", min: 1, max: 20, step: 1, isFloat: false },
];

// ORC: fine-grained orchestration controls
const ORC_PARAMS: ParamConfig[] = [
  { key: "max_tours_par_demande", labelKey: "bot.journey.maxToursParDemande", min: 1, max: 10, step: 1, isFloat: false },
  { key: "max_duree_session_s", labelKey: "bot.journey.maxDureeSession", min: 120, max: 14400, step: 60, isFloat: false },
  { key: "max_tokens_llm_session", labelKey: "bot.journey.maxTokensLLM", min: 500, max: 100000, step: 500, isFloat: false },
];

export function BotJourney({ botId, config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [journey, setJourney] = useState<JourneyParams>({ ...config.journey });
  const [dirty, setDirty] = useState(false);

  const handleChange = (key: NumericJourneyKey, raw: string, isFloat: boolean) => {
    const val = isFloat ? parseFloat(raw) : parseInt(raw, 10);
    if (isNaN(val)) return;
    setJourney((prev) => ({ ...prev, [key]: val }));
    setDirty(true);
  };

  const handleSave = async () => {
    await updateConfig({ journey });
    setDirty(false);
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">{t("bot.journey.title")}</h3>

      <div className="space-y-4">
        {PARAMS.map((p) => {
          const value = journey[p.key];
          return (
            <div key={p.key} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
                  {t(p.labelKey)}
                </label>
                <span className="text-xs font-mono text-gray-500">
                  {p.isFloat ? (value as number).toFixed(2) : value}
                </span>
              </div>
              <input
                type="range"
                min={p.min}
                max={p.max}
                step={p.step}
                value={value}
                onChange={(e) => handleChange(p.key, e.target.value, p.isFloat)}
                className="w-full h-1.5 rounded-full appearance-none bg-gray-200 dark:bg-gray-700 accent-brand-500"
              />
              <div className="flex justify-between text-[10px] text-gray-400">
                <span>{p.min}</span>
                <span className="text-gray-300 dark:text-gray-600">
                  {t("bot.wizard.save")}: {p.isFloat ? JOURNEY_DEFAULTS[p.key].toFixed(2) : JOURNEY_DEFAULTS[p.key]}
                </span>
                <span>{p.max}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ORC: Orchestration fine-grained controls */}
      <h3 className="text-base font-semibold mt-8">{t("bot.journey.orcTitle")}</h3>
      <div className="space-y-4">
        {ORC_PARAMS.map((p) => {
          const value = journey[p.key];
          return (
            <div key={p.key} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
                  {t(p.labelKey)}
                </label>
                <span className="text-xs font-mono text-gray-500">
                  {p.isFloat ? (value as number).toFixed(2) : value}
                </span>
              </div>
              <input
                type="range"
                min={p.min}
                max={p.max}
                step={p.step}
                value={value as number}
                onChange={(e) => handleChange(p.key, e.target.value, p.isFloat)}
                className="w-full h-1.5 rounded-full appearance-none bg-gray-200 dark:bg-gray-700 accent-brand-500"
              />
              <div className="flex justify-between text-[10px] text-gray-400">
                <span>{p.min}</span>
                <span className="text-gray-300 dark:text-gray-600">
                  {t("bot.wizard.save")}: {p.isFloat ? (JOURNEY_DEFAULTS[p.key] as number).toFixed(2) : JOURNEY_DEFAULTS[p.key]}
                </span>
                <span>{p.max}</span>
              </div>
            </div>
          );
        })}

        {/* Toggle: prevenir_avant_derniere_demande */}
        <div className="flex items-center gap-3 mt-2">
          <input
            type="checkbox"
            id="prevenir_avant_derniere_demande"
            checked={journey.prevenir_avant_derniere_demande}
            onChange={(e) => {
              setJourney((prev) => ({ ...prev, prevenir_avant_derniere_demande: e.target.checked }));
              setDirty(true);
            }}
            className="rounded border-gray-300 text-brand-500 focus:ring-brand-500"
          />
          <label htmlFor="prevenir_avant_derniere_demande" className="text-xs text-gray-600 dark:text-gray-400">
            {t("bot.journey.prevenirAvantDerniere")}
          </label>
        </div>
      </div>

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}

      {/* LLM sub-step: BYO provider configuration */}
      <BotLLM botId={botId} config={config} updateConfig={updateConfig} saving={saving} />
    </div>
  );
}
