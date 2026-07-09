import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
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
        <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>{t("common.loading")}</p>
      </div>
    );
  }

  if (error || !config || !botId) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: "var(--error-fg)" }}>{error || "Bot not found"}</p>
      </div>
    );
  }

  const StepComponent = STEP_COMPONENTS[stepKey];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-3 px-6 py-3"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--surface-canvas)" }}
      >
        <button
          onClick={() => navigate("/bot")}
          className="p-1 rounded transition-colors"
          style={{ color: "var(--text-secondary)" }}
        >
          <ArrowLeft size={16} />
        </button>
        <h2 className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>{config.name}</h2>
        <div
          className="ml-auto text-xs font-mono"
          style={{ color: "var(--text-tertiary)" }}
        >
          {config.status === "published"
            ? t("bot.status.published")
            : t("bot.status.draft")}
        </div>
      </div>

      {/* Step navigation — prototype style: numbered dots with active border */}
      <div
        className="flex items-center gap-1 px-4 py-2 overflow-x-auto"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        {STEPS.map((key, idx) => {
          const isActive = idx === currentStep;
          const isCompleted = idx < currentStep;
          return (
            <button
              key={key}
              onClick={() => goToStep(idx)}
              className="flex items-center gap-2 px-3 py-2 text-[13px] font-medium transition-colors whitespace-nowrap"
              style={{
                borderBottom: isActive ? "2px solid var(--brand-primary)" : "2px solid transparent",
                color: isActive
                  ? "var(--text-primary)"
                  : isCompleted
                    ? "var(--text-secondary)"
                    : "var(--text-disabled)",
                cursor: "pointer",
              }}
            >
              <span
                className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-semibold"
                style={{
                  background: isActive
                    ? "var(--brand-primary)"
                    : isCompleted
                      ? "var(--brand-primary-tint)"
                      : "var(--surface-sunken)",
                  color: isActive
                    ? "var(--text-on-brand)"
                    : isCompleted
                      ? "var(--green-700)"
                      : "var(--text-tertiary)",
                }}
              >
                {isCompleted ? "\u2713" : idx + 1}
              </span>
              {t(`bot.wizard.step${idx + 1}`)}
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
      <div
        className="flex items-center justify-between px-6 py-3"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
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
