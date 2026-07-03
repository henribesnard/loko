import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { useBotConfig } from "@/hooks/useBotConfig";
import { BotProject } from "./wizard/BotProject";
import { BotIntents } from "./wizard/BotIntents";
import { BotKnowledge } from "./wizard/BotKnowledge";
import { BotJourney } from "./wizard/BotJourney";
import { BotMessages } from "./wizard/BotMessages";
import { BotPublish } from "./wizard/BotPublish";

const STEPS = ["project", "intents", "knowledge", "journey", "messages", "publish"] as const;
type StepKey = (typeof STEPS)[number];

const STEP_COMPONENTS: Record<StepKey, React.ComponentType<WizardStepProps>> = {
  project: BotProject,
  intents: BotIntents,
  knowledge: BotKnowledge,
  journey: BotJourney,
  messages: BotMessages,
  publish: BotPublish,
};

export interface WizardStepProps {
  botId: string;
  config: NonNullable<ReturnType<typeof useBotConfig>["config"]>;
  updateConfig: ReturnType<typeof useBotConfig>["updateConfig"];
  saving: boolean;
}

export function BotWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: botId, step: stepParam } = useParams<{ id: string; step?: string }>();
  const { config, loading, error, saving, updateConfig } = useBotConfig(botId);

  const currentStep = useMemo(() => {
    const idx = STEPS.indexOf(stepParam as StepKey);
    return idx >= 0 ? idx : 0;
  }, [stepParam]);

  const stepKey = STEPS[currentStep];

  const goToStep = (index: number) => {
    const key = STEPS[index];
    navigate(`/bot/${botId}/wizard/${key}`, { replace: true });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      </div>
    );
  }

  if (error || !config || !botId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-red-500">{error || "Bot not found"}</p>
      </div>
    );
  }

  const StepComponent = STEP_COMPONENTS[stepKey];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-gray-200 dark:border-gray-800">
        <button
          onClick={() => navigate("/bot")}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <h2 className="text-sm font-semibold truncate">{config.name}</h2>
        <div className="ml-auto text-xs text-gray-400">
          {config.status === "published"
            ? t("bot.status.published")
            : t("bot.status.draft")}
        </div>
      </div>

      {/* Step navigation */}
      <div className="flex items-center gap-1 px-6 py-3 border-b border-gray-200 dark:border-gray-800 overflow-x-auto">
        {STEPS.map((key, idx) => {
          const isActive = idx === currentStep;
          const isCompleted = idx < currentStep;
          return (
            <button
              key={key}
              onClick={() => goToStep(idx)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap",
                isActive
                  ? "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                  : isCompleted
                    ? "text-brand-600 dark:text-brand-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                    : "text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800",
              )}
            >
              {isCompleted && <Check size={12} />}
              <span>
                {idx + 1}. {t(`bot.wizard.step${idx + 1}`)}
              </span>
            </button>
          );
        })}
      </div>

      {/* Step content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6">
          <StepComponent
            botId={botId}
            config={config}
            updateConfig={updateConfig}
            saving={saving}
          />
        </div>
      </div>

      {/* Footer navigation */}
      <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 dark:border-gray-800">
        <Button
          variant="ghost"
          size="sm"
          disabled={currentStep === 0}
          onClick={() => goToStep(currentStep - 1)}
        >
          {t("bot.wizard.prev")}
        </Button>
        <div className="flex gap-2">
          {currentStep < STEPS.length - 1 ? (
            <Button size="sm" onClick={() => goToStep(currentStep + 1)}>
              {t("bot.wizard.next")}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => navigate(`/bot/${botId}/playground`)}
            >
              {t("bot.playground.title")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
