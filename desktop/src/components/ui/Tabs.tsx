import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface Tab {
  key: string;
  label: string;
  icon?: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
  direction?: "vertical" | "horizontal";
}

export function Tabs({ tabs, active, onChange, direction = "vertical" }: TabsProps) {
  const isVertical = direction === "vertical";

  return (
    <nav
      className={cn("flex gap-0.5", isVertical ? "flex-col" : "flex-row")}
      role="tablist"
      aria-orientation={isVertical ? "vertical" : "horizontal"}
    >
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={cn(
              "flex items-center gap-2 px-3 py-2 text-[13px] font-medium transition-colors text-left",
              isVertical ? "w-full" : "",
            )}
            style={{
              borderRadius: "var(--radius-sm)",
              background: isActive ? "var(--brand-primary-tint)" : "transparent",
              color: isActive ? "var(--green-700)" : "var(--text-secondary)",
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
