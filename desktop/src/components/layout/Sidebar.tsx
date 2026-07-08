import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { Bot, Globe, LogOut } from "lucide-react";
import { cn } from "@/lib/cn";

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
    <aside className="w-56 flex flex-col border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      {/* Logo */}
      <div className="px-5 py-4 flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
          <span className="text-white font-bold text-sm">L</span>
        </div>
        <div>
          <div className="font-semibold text-sm">{t("app.title")}</div>
          <div className="text-[11px] text-gray-400">{t("app.subtitle")}</div>
        </div>
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
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors",
                active
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800",
              )}
            >
              <link.icon size={16} />
              {link.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-gray-200 dark:border-gray-800 space-y-1">
        <button
          onClick={toggleLang}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          <Globe size={14} />
          {i18n.language.toUpperCase()}
        </button>
        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500 hover:text-red-600 dark:hover:text-red-400 transition-colors"
          >
            <LogOut size={14} />
            {t("auth.logout")}
          </button>
        )}
      </div>
    </aside>
  );
}
