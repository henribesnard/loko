import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Check,
  CheckCircle,
  Copy,
  Key,
  Plus,
  Rocket,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { WizardStepProps } from "../BotWizard";

interface PublishCheck {
  key: string;
  labelKey: string;
  ok: boolean;
}

const REQUIRED_SYSTEM_INTENTS = ["hors_perimetre", "demande_conseiller"];

export function BotPublish({ botId, config, updateConfig }: WizardStepProps) {
  const { t } = useTranslation();
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [publishSuccess, setPublishSuccess] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [addingSystemIntents, setAddingSystemIntents] = useState(false);
  const [systemIntentsAdded, setSystemIntentsAdded] = useState(false);

  const intentIds = new Set(config.intents.map((i) => i.id));
  const missingSystemIntents = REQUIRED_SYSTEM_INTENTS.filter(
    (id) => !intentIds.has(id),
  );
  const hasAllSystemIntents = missingSystemIntents.length === 0;

  // Pre-publish checks
  const checks: PublishCheck[] = [
    {
      key: "systemIntents",
      labelKey: "bot.publish.checkSystemIntents",
      ok: hasAllSystemIntents,
    },
    {
      key: "intents",
      labelKey: "bot.publish.checkIntents",
      ok: config.intents.filter((i) => !i.is_system).length > 0,
    },
    {
      key: "examples",
      labelKey: "bot.publish.checkExamples",
      ok: config.intents
        .filter((i) => !i.is_system)
        .every((i) => i.examples.length >= 8),
    },
    {
      key: "trained",
      labelKey: "bot.publish.checkTrained",
      ok: config.status === "published", // Approximation — la vraie vérif est backend
    },
  ];

  const handleAddSystemIntents = async () => {
    setAddingSystemIntents(true);
    setPublishError(null);
    try {
      const res = await api<{ added: string[] }>(
        `/api/bot/${botId}/system-intents/ensure`,
        { method: "POST" },
      );
      if (res.added.length > 0) {
        setSystemIntentsAdded(true);
        // Refresh config to reflect new intents
        const updated = await api<typeof config>(`/api/bot/${botId}`);
        updateConfig({ intents: updated.intents });
      }
    } catch (err) {
      if (err instanceof Error) {
        setPublishError(err.message);
      }
    } finally {
      setAddingSystemIntents(false);
    }
  };

  const handlePublish = async () => {
    setPublishing(true);
    setPublishError(null);
    try {
      await api(`/api/bot/${botId}/publish`, { method: "POST" });
      setPublishSuccess(true);
      // Refresh config
      const updated = await api<typeof config>(`/api/bot/${botId}`);
      updateConfig({ name: updated.name }); // Triggers refresh
    } catch (err) {
      if (err instanceof Error) {
        setPublishError(err.message);
      }
    } finally {
      setPublishing(false);
    }
  };

  const handleGenerateKey = async () => {
    try {
      const res = await api<{ raw_key: string; key_id: string }>(
        `/api/bot/${botId}/api-keys`,
        {
          method: "POST",
          body: JSON.stringify({ label: "default", allowed_origins: ["*"] }),
        },
      );
      sessionStorage.setItem(`loko_api_key_${botId}`, res.raw_key);
      setApiKey(res.raw_key);
    } catch (err) {
      if (err instanceof Error) {
        setPublishError(err.message);
      }
    }
  };

  const widgetSnippet = `<script
  src="${window.location.origin}/widget/loko-widget.js"
  data-bot-id="${botId}"
  data-api-url="${window.location.origin}"${apiKey ? `\n  data-api-key="${apiKey}"` : ""}
></script>`;

  const copySnippet = () => {
    navigator.clipboard.writeText(widgetSnippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">{t("bot.publish.title")}</h3>

      {/* Checks */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.publish.checks")}
        </p>
        {checks.map((check) => (
          <div
            key={check.key}
            className="flex items-center gap-2 text-xs"
          >
            {check.ok ? (
              <CheckCircle size={14} className="text-green-500" />
            ) : (
              <AlertCircle size={14} className="text-amber-500" />
            )}
            <span
              className={cn(
                check.ok
                  ? "text-green-700 dark:text-green-400"
                  : "text-amber-700 dark:text-amber-400",
              )}
            >
              {t(check.labelKey)}
            </span>
          </div>
        ))}
      </div>

      {/* Missing system intents: explanation + auto-add button */}
      {!hasAllSystemIntents && (
        <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 space-y-2">
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {t("bot.publish.missingSystemIntents", {
              missing: missingSystemIntents.join(", "),
            })}
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleAddSystemIntents}
            disabled={addingSystemIntents}
          >
            <Plus size={14} />
            {t("bot.publish.addSystemIntents")}
          </Button>
        </div>
      )}

      {/* System intents added success message */}
      {systemIntentsAdded && hasAllSystemIntents && (
        <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-xs text-green-700 dark:text-green-400 flex items-center gap-2">
          <Check size={14} />
          {t("bot.publish.systemIntentsAdded")}
        </div>
      )}

      {/* Publish button */}
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={handlePublish}
          disabled={publishing || config.status === "published"}
        >
          <Rocket size={14} />
          {config.status === "published"
            ? t("bot.status.published")
            : t("bot.publish.publishBtn")}
        </Button>
        {publishSuccess && (
          <span className="text-xs text-green-600 flex items-center gap-1">
            <Check size={12} />
            {t("bot.publish.publishSuccess")}
          </span>
        )}
      </div>

      {publishError && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-xs text-red-700 dark:text-red-400">
          {publishError}
        </div>
      )}

      {/* API Key */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.publish.apiKey")}
        </p>
        {apiKey ? (
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-xs font-mono break-all">
              {apiKey}
            </code>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                navigator.clipboard.writeText(apiKey);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
            >
              <Copy size={12} />
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" onClick={handleGenerateKey}>
            <Key size={14} />
            {t("bot.publish.generateKey")}
          </Button>
        )}
      </div>

      {/* Widget snippet */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.publish.widgetSnippet")}
        </p>
        <div className="relative">
          <pre className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
            {widgetSnippet}
          </pre>
          <button
            onClick={copySnippet}
            className="absolute top-2 right-2 p-1.5 rounded bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-xs"
          >
            {copied ? t("common.copied") : t("bot.publish.copySnippet")}
          </button>
        </div>
      </div>
    </div>
  );
}
