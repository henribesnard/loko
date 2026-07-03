import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Database, Tag } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { WizardStepProps } from "../BotWizard";

export function BotKnowledge({ config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [collection, setCollection] = useState(config.knowledge_collection);
  const [filter, setFilter] = useState(config.confidentiality_filter.join(", "));
  const [dirty, setDirty] = useState(false);

  const handleSave = async () => {
    await updateConfig({
      knowledge_collection: collection,
      confidentiality_filter: filter
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
    setDirty(false);
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">{t("bot.knowledge.title")}</h3>

      {/* Collection */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <Database size={14} />
          {t("bot.knowledge.collection")}
        </div>
        <Input
          placeholder={t("bot.knowledge.collectionPlaceholder")}
          value={collection}
          onChange={(e) => {
            setCollection(e.target.value);
            setDirty(true);
          }}
        />
      </div>

      {/* Confidentiality filter */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <Tag size={14} />
          {t("bot.knowledge.confidentiality")}
        </div>
        <Input
          placeholder="public, interne"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setDirty(true);
          }}
        />
        <p className="text-xs text-gray-400">
          Tags séparés par virgule. Seuls les documents avec ces tags seront utilisés.
        </p>
      </div>

      {/* Document tagging overview */}
      {config.intents.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
            {t("bot.knowledge.tagging")}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {config.intents
              .filter((i) => !i.is_system)
              .map((intent) => (
                <div
                  key={intent.id}
                  className="flex items-center gap-2 px-3 py-2 rounded border border-gray-200 dark:border-gray-700 text-xs"
                >
                  <span className="w-2 h-2 rounded-full bg-brand-400" />
                  <span className="font-medium">{intent.label || intent.id}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}
    </div>
  );
}
