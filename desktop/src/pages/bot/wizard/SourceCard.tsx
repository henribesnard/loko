import { useTranslation } from "react-i18next";
import { Globe2, FileText, Type, Trash2, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export interface SourceData {
  id: string;
  type: "web" | "file" | "text";
  label: string;
  start_url: string;
  document_count: number;
  last_ingest: {
    at: string;
    discovered: number;
    ingested: number;
    untagged: number;
    errors: number;
  } | null;
}

interface SourceCardProps {
  source: SourceData;
  onRediscover: (id: string) => void;
  onDelete: (id: string) => void;
}

const TYPE_ICONS = {
  web: Globe2,
  file: FileText,
  text: Type,
} as const;

const TYPE_LABELS = {
  web: "bot.sources.typeWeb",
  file: "bot.sources.typeFile",
  text: "bot.sources.typeText",
} as const;

export function SourceCard({ source, onRediscover, onDelete }: SourceCardProps) {
  const { t } = useTranslation();
  const Icon = TYPE_ICONS[source.type];
  const li = source.last_ingest;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={16} className="shrink-0 text-gray-500" />
          <span className="text-sm font-medium truncate">{source.label}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 shrink-0">
            {t(TYPE_LABELS[source.type])}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {source.type === "web" && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onRediscover(source.id)}
              title={t("bot.sources.rediscover")}
            >
              <RefreshCw size={14} />
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onDelete(source.id)}
            title={t("bot.sources.deleteSource")}
            className="text-red-500 hover:text-red-600"
          >
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      {source.type === "web" && source.start_url && (
        <p className="text-xs text-gray-400 truncate">{source.start_url}</p>
      )}

      {li && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span>
            {li.ingested} {t("bot.sources.ingested")}
          </span>
          <span>
            {li.discovered} {t("bot.sources.discovered")}
          </span>
          {li.errors > 0 && (
            <span className="text-red-500">
              {li.errors} {t("bot.sources.errors")}
            </span>
          )}
          {li.untagged > 0 && (
            <span
              className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded",
                "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
              )}
            >
              <AlertTriangle size={10} />
              {li.untagged} {t("bot.sources.untagged")}
            </span>
          )}
        </div>
      )}

      {!li && (
        <p className="text-xs text-gray-400 italic">
          {source.document_count} {t("bot.sources.documents")}
        </p>
      )}
    </div>
  );
}
