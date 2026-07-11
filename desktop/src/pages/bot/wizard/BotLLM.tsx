import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { WizardStepProps } from "../BotWizard";

const PRESETS = [
  { value: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1" },
  { value: "mistral", label: "Mistral", baseUrl: "https://api.mistral.ai/v1" },
  { value: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1" },
  { value: "ollama", label: "Ollama (local)", baseUrl: "http://localhost:11434/v1" },
  { value: "vllm", label: "vLLM (local)", baseUrl: "http://localhost:8000/v1" },
  { value: "autre", label: "Autre", baseUrl: "" },
] as const;

interface TestResult {
  ok: boolean;
  model?: string;
  ttfb_ms?: number;
  total_ms?: number;
  error_code?: string;
  detail?: string;
}

export function BotLLM({ botId, config, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const llm = config.llm;

  const [source, setSource] = useState<"platform" | "custom">(llm.provider_source || "platform");
  const [preset, setPreset] = useState<string>(llm.preset || "openai");
  const [baseUrl, setBaseUrl] = useState(llm.base_url || "");
  const [model, setModel] = useState(llm.model || "");
  const [apiKey, setApiKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [dirty, setDirty] = useState(false);

  const handlePresetChange = (newPreset: string) => {
    setPreset(newPreset);
    const found = PRESETS.find((p) => p.value === newPreset);
    if (found && found.baseUrl) {
      setBaseUrl(found.baseUrl);
    }
    setDirty(true);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`/api/bot/${botId}/llm/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: baseUrl,
          model: model,
          api_key: apiKey,
        }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch {
      setTestResult({ ok: false, error_code: "unreachable", detail: "Network error" });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    const payload: Record<string, unknown> = {
      provider_source: source,
    };
    if (source === "custom") {
      payload.preset = preset;
      payload.base_url = baseUrl;
      payload.model = model;
      if (apiKey) {
        payload.api_key = apiKey;
      }
    }

    try {
      await fetch(`/api/bot/${botId}/llm`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setApiKey("");
      setDirty(false);
    } catch {
      // Error handling via useBotConfig
    }
  };

  const isPlatform = source === "platform";

  if (isPlatform) {
    return (
      <div className="space-y-4 mt-6 p-4 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
        <h4 className="text-sm font-semibold">{t("bot.llm.title")}</h4>
        <div className="flex gap-3">
          <Button
            size="sm"
            variant="primary"
            onClick={() => { setSource("platform"); setDirty(true); }}
          >
            {t("bot.llm.platform")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => { setSource("custom"); setDirty(true); }}
          >
            {t("bot.llm.custom")}
          </Button>
        </div>
        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          {t("bot.llm.platform")} — {llm.model}
        </p>
        {dirty && (
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {t("bot.wizard.save")}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4 mt-6 p-4 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
      <h4 className="text-sm font-semibold">{t("bot.llm.title")}</h4>

      <div className="flex gap-3">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => { setSource("platform"); setDirty(true); }}
        >
          {t("bot.llm.platform")}
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={() => { setSource("custom"); setDirty(true); }}
        >
          {t("bot.llm.custom")}
        </Button>
      </div>

      {/* Preset selector */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("bot.llm.preset")}
        </label>
        <select
          value={preset}
          onChange={(e) => handlePresetChange(e.target.value)}
          className="w-full text-sm px-3 py-2 rounded-md"
          style={{
            border: "1px solid var(--border-default)",
            background: "var(--surface-raised)",
            color: "var(--text-primary)",
          }}
        >
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      {/* Base URL */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("bot.llm.baseUrl")}
        </label>
        <Input
          value={baseUrl}
          onChange={(e) => { setBaseUrl(e.target.value); setDirty(true); }}
          placeholder={t("bot.llm.baseUrlPlaceholder")}
        />
      </div>

      {/* Model */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("bot.llm.model")}
        </label>
        <Input
          value={model}
          onChange={(e) => { setModel(e.target.value); setDirty(true); }}
          placeholder={t("bot.llm.modelPlaceholder")}
        />
      </div>

      {/* API Key */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("bot.llm.apiKey")}
        </label>
        <Input
          type="password"
          value={apiKey}
          onChange={(e) => { setApiKey(e.target.value); setDirty(true); }}
          placeholder={
            llm.api_key_hint
              ? t("bot.llm.apiKeyHint", { hint: llm.api_key_hint })
              : t("bot.llm.apiKeyPlaceholder")
          }
        />
      </div>

      {/* Test connection */}
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="ghost"
          onClick={handleTest}
          disabled={testing || !baseUrl || !model || (!apiKey && !llm.api_key_set)}
        >
          {testing ? "..." : t("bot.llm.testConnection")}
        </Button>
        {testResult && (
          <span
            className="text-xs font-medium"
            style={{ color: testResult.ok ? "var(--green-700)" : "var(--error-fg)" }}
          >
            {testResult.ok
              ? `${t("bot.llm.testSuccess")} — ${t("bot.llm.ttfb")}: ${testResult.ttfb_ms}ms`
              : `${t("bot.llm.testFailed")}: ${testResult.error_code}`}
          </span>
        )}
      </div>

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}
    </div>
  );
}
