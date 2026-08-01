/**
 * LOKO — Bot sub-navigation bar.
 *
 * Horizontal tabs: Dashboard / Monitoring / Replay.
 * Reused on BotDashboard, BotMonitoring pages.
 */
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { cn } from "@/lib/cn";

interface Tab {
  key: string;
  i18nKey: string;
  path: (botId: string) => string;
}

const TABS: Tab[] = [
  { key: "dashboard", i18nKey: "nav.dashboard", path: (id) => `/bot/${id}/dashboard` },
  { key: "monitoring", i18nKey: "monitoring.title", path: (id) => `/bot/${id}/monitoring` },
];

interface BotSubNavProps {
  active: "dashboard" | "monitoring";
}

export function BotSubNav({ active }: BotSubNavProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: botId } = useParams<{ id: string }>();

  if (!botId) return null;

  return (
    <nav
      className="flex gap-6 px-7 border-b"
      style={{
        background: "var(--surface-card)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => navigate(tab.path(botId))}
            className={cn(
              "py-3 text-[13px] font-semibold border-b-2 transition-colors bg-transparent cursor-pointer",
              isActive
                ? "border-brand-500 text-[var(--text-primary)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
            style={{ borderBottomWidth: 2 }}
          >
            {t(tab.i18nKey)}
          </button>
        );
      })}
    </nav>
  );
}
