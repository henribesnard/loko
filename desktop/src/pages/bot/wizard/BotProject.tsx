import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import type { WizardStepProps } from "../BotWizard";
import type { Channel, BotLanguage, ToneProfile } from "@/types/bot";

const CHANNELS: { value: Channel; labelKey: string }[] = [
  { value: "widget", labelKey: "bot.project.channelWidget" },
  { value: "api", labelKey: "bot.project.channelApi" },
  { value: "both", labelKey: "bot.project.channelBoth" },
];

const LANGUAGES: { value: BotLanguage; label: string }[] = [
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
  { value: "auto", label: "Auto" },
];

const TONES: { value: ToneProfile; labelKey: string }[] = [
  { value: "formel", labelKey: "bot.project.toneFormel" },
  { value: "chaleureux", labelKey: "bot.project.toneChaleureux" },
  { value: "neutre", labelKey: "bot.project.toneNeutre" },
];

export function BotProject({ config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(config.name);
  const [channel, setChannel] = useState<Channel>(config.channel);
  const [language, setLanguage] = useState<BotLanguage>(config.language);
  const [tone, setTone] = useState<ToneProfile>(config.tone_profile);
  const [dirty, setDirty] = useState(false);

  const handleSave = async () => {
    await updateConfig({ name, channel, language, tone_profile: tone });
    setDirty(false);
  };

  const update = <T,>(setter: React.Dispatch<React.SetStateAction<T>>, val: T) => {
    setter(val);
    setDirty(true);
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">{t("bot.project.title")}</h3>

      <Input
        label={t("bot.project.name")}
        placeholder={t("bot.project.namePlaceholder")}
        value={name}
        onChange={(e) => update(setName, e.target.value)}
      />

      {/* Channel */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.project.channel")}
        </label>
        <div className="flex gap-2">
          {CHANNELS.map((ch) => (
            <button
              key={ch.value}
              onClick={() => update(setChannel, ch.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                channel === ch.value
                  ? "bg-brand-50 border-brand-300 text-brand-700 dark:bg-brand-900/30 dark:border-brand-600 dark:text-brand-300"
                  : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
            >
              {t(ch.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Language */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.project.language")}
        </label>
        <div className="flex gap-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              onClick={() => update(setLanguage, lang.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                language === lang.value
                  ? "bg-brand-50 border-brand-300 text-brand-700 dark:bg-brand-900/30 dark:border-brand-600 dark:text-brand-300"
                  : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tone */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.project.tone")}
        </label>
        <div className="flex gap-2">
          {TONES.map((tn) => (
            <button
              key={tn.value}
              onClick={() => update(setTone, tn.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                tone === tn.value
                  ? "bg-brand-50 border-brand-300 text-brand-700 dark:bg-brand-900/30 dark:border-brand-600 dark:text-brand-300"
                  : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
            >
              {t(tn.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}
    </div>
  );
}
