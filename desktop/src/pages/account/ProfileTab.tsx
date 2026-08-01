import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { useAccountSettings } from "@/hooks/useAccountSettings";

interface Props {
  settings: ReturnType<typeof useAccountSettings>;
}

export function ProfileTab({ settings }: Props) {
  const { t } = useTranslation();
  const { profile, updateProfile, resendVerification } = settings;
  const [name, setName] = useState(profile?.display_name || "");
  const [language, setLanguage] = useState(profile?.language || "fr");
  const [tz, setTz] = useState(profile?.timezone || "Europe/Paris");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [resending, setResending] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await updateProfile({ display_name: name, language, timezone: tz });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      await resendVerification();
    } finally {
      setResending(false);
    }
  };

  const timezones = [
    "Europe/Paris",
    "Europe/London",
    "America/New_York",
    "America/Los_Angeles",
    "Asia/Tokyo",
    "UTC",
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
        {t("account.profile.title")}
      </h2>

      <Input
        label={t("account.profile.name")}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />

      {/* Email (read-only) */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("account.profile.email")}
        </label>
        <div className="flex items-center gap-2">
          <span className="text-sm" style={{ color: "var(--text-primary)" }}>
            {profile?.email}
          </span>
          <Badge
            label={profile?.email_verified_at ? t("account.profile.verified") : t("account.profile.unverified")}
            variant={profile?.email_verified_at ? "success" : "warning"}
          />
          {!profile?.email_verified_at && (
            <button
              onClick={handleResend}
              disabled={resending}
              className="text-xs underline"
              style={{ color: "var(--text-link)" }}
            >
              {t("account.profile.resendVerify")}
            </button>
          )}
        </div>
      </div>

      {/* Language */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("account.profile.language")}
        </label>
        <div className="flex gap-1">
          {(["fr", "en"] as const).map((lang) => (
            <button
              key={lang}
              onClick={() => setLanguage(lang)}
              className="px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                borderRadius: "var(--radius-sm)",
                background: language === lang ? "var(--brand-primary)" : "var(--surface-sunken)",
                color: language === lang ? "white" : "var(--text-secondary)",
              }}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Timezone */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {t("account.profile.timezone")}
        </label>
        <select
          value={tz}
          onChange={(e) => setTz(e.target.value)}
          className="w-full rounded-[var(--radius-sm)] border border-[var(--border-default)] px-3 py-2 text-sm bg-[var(--surface-page)] text-[var(--text-primary)]"
        >
          {timezones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? t("account.profile.saving") : saved ? t("account.profile.saved") : t("account.profile.save")}
        </Button>
      </div>
    </div>
  );
}
