import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Intent } from "@/types/bot";

interface CoverageBarProps {
  intents: Intent[];
  documents: { bot_intents: string[] }[];
}

export function CoverageBar({ intents, documents }: CoverageBarProps) {
  const { t } = useTranslation();

  const userIntents = intents.filter((i) => !i.is_system);
  if (userIntents.length === 0) return null;

  const counts = new Map<string, number>();
  for (const intent of userIntents) counts.set(intent.id, 0);
  for (const doc of documents) {
    for (const id of doc.bot_intents) {
      if (counts.has(id)) counts.set(id, counts.get(id)! + 1);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-[var(--text-secondary)]">
        {t("bot.knowledge.coverage.title")}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {userIntents.map((intent) => {
          const count = counts.get(intent.id) || 0;
          const isZero = count === 0;
          const isLow = count > 0 && count < 2;
          return (
            <span
              key={intent.id}
              className={cn(
                "inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium",
                isZero &&
                  "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
                isLow &&
                  "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
                !isZero &&
                  !isLow &&
                  "bg-[var(--surface-sunken)] text-[var(--text-secondary)]",
              )}
              title={
                isZero || isLow
                  ? t("bot.knowledge.coverage.warn", {
                      label: intent.label || intent.id,
                      count,
                    })
                  : undefined
              }
            >
              {(isZero || isLow) && <AlertTriangle size={10} />}
              {intent.label || intent.id} : {count}
            </span>
          );
        })}
      </div>
    </div>
  );
}
