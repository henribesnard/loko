import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { User, Shield, Users, CreditCard, Lock } from "lucide-react";
import { Tabs } from "@/components/ui/Tabs";
import { useAccountSettings } from "@/hooks/useAccountSettings";
import { ProfileTab } from "./ProfileTab";
import { SecurityTab } from "./SecurityTab";
import { TeamTab } from "./TeamTab";
import { BillingTab } from "./BillingTab";
import { PrivacyTab } from "./PrivacyTab";

const TAB_KEYS = ["profile", "security", "team", "billing", "privacy"] as const;

export function AccountSettings() {
  const { tab } = useParams<{ tab?: string }>();
  const initial = TAB_KEYS.includes(tab as any) ? (tab as string) : "profile";
  const [activeTab, setActiveTab] = useState(initial);
  const { t } = useTranslation();
  const settings = useAccountSettings();

  const tabs = [
    { key: "profile", label: t("account.tabs.profile"), icon: <User size={16} /> },
    { key: "security", label: t("account.tabs.security"), icon: <Shield size={16} /> },
    { key: "team", label: t("account.tabs.team"), icon: <Users size={16} /> },
    { key: "billing", label: t("account.tabs.billing"), icon: <CreditCard size={16} /> },
    { key: "privacy", label: t("account.tabs.privacy"), icon: <Lock size={16} /> },
  ];

  if (settings.loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>
          {t("common.loading")}
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1080px] p-8">
        <h1
          className="text-lg font-semibold mb-6"
          style={{ color: "var(--text-primary)" }}
        >
          {t("account.title")}
        </h1>
        <div className="grid gap-8" style={{ gridTemplateColumns: "220px 1fr" }}>
          <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} direction="vertical" />
          <div className="min-w-0">
            {activeTab === "profile" && <ProfileTab settings={settings} />}
            {activeTab === "security" && <SecurityTab settings={settings} />}
            {activeTab === "team" && <TeamTab settings={settings} />}
            {activeTab === "billing" && <BillingTab settings={settings} />}
            {activeTab === "privacy" && <PrivacyTab settings={settings} />}
          </div>
        </div>
      </div>
    </div>
  );
}
