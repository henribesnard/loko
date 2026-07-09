import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { Bot, Globe, LogOut } from "lucide-react";
import { cn } from "@/lib/cn";
import { LokoLockup } from "@/components/ui/LokoLockup";

interface SidebarProps {
  onLogout?: () => void;
}

export function Sidebar({ onLogout }: SidebarProps) {
  const { t, i18n } = useTranslation();
  const { pathname } = useLocation();

  const links = [
    { to: "/bot", icon: Bot, label: t("nav.bots") },
  ];

  const toggleLang = () => {
    const next = i18n.language === "fr" ? "en" : "fr";
    i18n.changeLanguage(next);
    localStorage.setItem("loko-lang", next);
  };

  return (
    <aside
      className="w-56 flex flex-col"
      style={{
        borderRight: "1px solid var(--border-subtle)",
        background: "var(--surface-canvas)",
      }}
    >
      {/* Logo */}
      <div className="px-5 py-4 flex items-center gap-2.5">
        <LokoLockup height={24} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1">
        {links.map((link) => {
          const active = pathname.startsWith(link.to);
          return (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium transition-colors",
              )}
              style={{
                borderRadius: "var(--radius-sm)",
                background: active ? "var(--brand-primary-tint)" : "transparent",
                color: active ? "var(--green-700)" : "var(--text-secondary)",
              }}
            >
              <link.icon size={16} />
              {link.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div
        className="px-3 py-3 space-y-1"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <button
          onClick={toggleLang}
          className="flex items-center gap-2 px-3 py-1.5 text-xs transition-colors"
          style={{ color: "var(--text-tertiary)" }}
        >
          <Globe size={14} />
          {i18n.language.toUpperCase()}
        </button>
        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-2 px-3 py-1.5 text-xs transition-colors hover:text-red-600"
            style={{ color: "var(--text-tertiary)" }}
          >
            <LogOut size={14} />
            {t("auth.logout")}
          </button>
        )}
      </div>
    </aside>
  );
}
