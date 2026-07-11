import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Shield, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { GuardrailRule, GuardrailsConfig } from "@/types/bot";

interface BotGuardrailsProps {
  botId: string;
  guardrails?: GuardrailsConfig;
  onSave: (config: Record<string, unknown>) => Promise<unknown>;
  saving: boolean;
}

const CATEGORIES = [
  { value: "injection", label: "Injection" },
  { value: "dangereux", label: "Dangereux" },
  { value: "donnees_tiers", label: "Données tiers" },
  { value: "juridique_medical", label: "Juridique/Médical" },
  { value: "custom", label: "Personnalisé" },
] as const;

const ACTIONS = [
  { value: "refuser", label: "Refuser" },
  { value: "refuser_et_compter", label: "Refuser + compter" },
  { value: "escalader", label: "Escalader" },
] as const;

const DEFAULT_CONFIG: GuardrailsConfig = {
  enabled: true,
  rules: [],
  max_infractions: 2,
  action_apres_max: "fin_ferme",
  seuil_rejet_fort: 0.85,
  block_low_grounding: false,
};

export function BotGuardrails({ guardrails, onSave, saving }: BotGuardrailsProps) {
  const { t } = useTranslation();
  const [config, setConfig] = useState<GuardrailsConfig>(guardrails || DEFAULT_CONFIG);
  const [dirty, setDirty] = useState(false);
  const [newRule, setNewRule] = useState({
    pattern: "",
    category: "custom" as string,
    action: "refuser_et_compter" as string,
  });

  const handleToggle = () => {
    setConfig((prev) => ({ ...prev, enabled: !prev.enabled }));
    setDirty(true);
  };

  const handleAddRule = () => {
    if (!newRule.pattern.trim()) return;

    const rule: GuardrailRule = {
      id: `custom_${Date.now()}`,
      pattern: newRule.pattern,
      category: newRule.category as GuardrailRule["category"],
      action: newRule.action as GuardrailRule["action"],
      enabled: true,
      is_system: false,
    };

    setConfig((prev) => ({ ...prev, rules: [...prev.rules, rule] }));
    setNewRule({ pattern: "", category: "custom", action: "refuser_et_compter" });
    setDirty(true);
  };

  const handleRemoveRule = (ruleId: string) => {
    setConfig((prev) => ({
      ...prev,
      rules: prev.rules.filter((r) => r.id !== ruleId),
    }));
    setDirty(true);
  };

  const handleSave = async () => {
    await onSave({ guardrails: config } as any);
    setDirty(false);
  };

  return (
    <div className="space-y-4 mt-8 p-4 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={16} style={{ color: "var(--text-secondary)" }} />
          <h4 className="text-sm font-semibold">{t("bot.guardrails.title")}</h4>
        </div>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={handleToggle}
            className="rounded border-gray-300 text-brand-500 focus:ring-brand-500"
          />
          {t("bot.guardrails.enabled")}
        </label>
      </div>

      {config.enabled && (
        <>
          {/* Settings */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("bot.guardrails.maxInfractions")}
              </label>
              <input
                type="number"
                min={1}
                max={5}
                value={config.max_infractions}
                onChange={(e) => {
                  setConfig((prev) => ({ ...prev, max_infractions: parseInt(e.target.value) || 2 }));
                  setDirty(true);
                }}
                className="w-full text-sm px-3 py-2 rounded-md"
                style={{
                  border: "1px solid var(--border-default)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                }}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("bot.guardrails.actionApresMax")}
              </label>
              <select
                value={config.action_apres_max}
                onChange={(e) => {
                  setConfig((prev) => ({ ...prev, action_apres_max: e.target.value as "fin_ferme" | "escalade" }));
                  setDirty(true);
                }}
                className="w-full text-sm px-3 py-2 rounded-md"
                style={{
                  border: "1px solid var(--border-default)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                }}
              >
                <option value="fin_ferme">{t("bot.guardrails.finFerme")}</option>
                <option value="escalade">{t("bot.guardrails.escalade")}</option>
              </select>
            </div>
          </div>

          {/* Rules list */}
          <div className="space-y-2">
            <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
              {t("bot.guardrails.rules")}
            </label>

            {config.rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center gap-2 p-2 rounded text-xs"
                style={{ background: "var(--surface-sunken)" }}
              >
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{
                    background: rule.is_system ? "var(--brand-primary-tint)" : "var(--surface-raised)",
                    color: rule.is_system ? "var(--brand-primary)" : "var(--text-secondary)",
                  }}
                >
                  {rule.category}
                </span>
                <code className="flex-1 font-mono text-[11px] truncate" title={rule.pattern}>
                  {rule.pattern}
                </code>
                <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                  {rule.action}
                </span>
                {!rule.is_system && (
                  <button onClick={() => handleRemoveRule(rule.id)}>
                    <Trash2 size={12} style={{ color: "var(--error-fg)" }} />
                  </button>
                )}
                {rule.is_system && (
                  <span className="text-[10px]" style={{ color: "var(--text-disabled)" }}>
                    {t("bot.guardrails.systemRule")}
                  </span>
                )}
              </div>
            ))}

            {/* Add new rule */}
            <div className="flex items-end gap-2 mt-2">
              <div className="flex-1 space-y-1">
                <Input
                  value={newRule.pattern}
                  onChange={(e) => setNewRule((prev) => ({ ...prev, pattern: e.target.value }))}
                  placeholder={t("bot.guardrails.pattern")}
                />
              </div>
              <select
                value={newRule.category}
                onChange={(e) => setNewRule((prev) => ({ ...prev, category: e.target.value }))}
                className="text-xs px-2 py-2 rounded-md"
                style={{
                  border: "1px solid var(--border-default)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                }}
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
              <select
                value={newRule.action}
                onChange={(e) => setNewRule((prev) => ({ ...prev, action: e.target.value }))}
                className="text-xs px-2 py-2 rounded-md"
                style={{
                  border: "1px solid var(--border-default)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                }}
              >
                {ACTIONS.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
              <Button size="sm" variant="ghost" onClick={handleAddRule} disabled={!newRule.pattern.trim()}>
                <Plus size={14} />
              </Button>
            </div>
          </div>
        </>
      )}

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}
    </div>
  );
}
