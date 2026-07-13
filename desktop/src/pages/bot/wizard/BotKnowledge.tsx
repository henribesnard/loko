import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Database, Plus, Tag } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { api } from "@/lib/api";
import { DocumentTagTable } from "./DocumentTagTable";
import { CoverageBar } from "./CoverageBar";
import { SourceCard, type SourceData } from "./SourceCard";
import { SourceWizardWeb } from "./SourceWizardWeb";
import type { WizardStepProps } from "../BotWizard";

interface KnowledgeDocument {
  doc_id: string;
  source_url: string;
  source_title: string;
  bot_intents: string[];
  bot_sub_motifs: string[];
  confidentiality: string;
}

type AddMode = null | "choose" | "web";

export function BotKnowledge({ botId, config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [collection, setCollection] = useState(config.knowledge_collection);
  const [filter, setFilter] = useState(config.confidentiality_filter.join(", "));
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [sources, setSources] = useState<SourceData[]>([]);
  const [dirty, setDirty] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>(null);
  const [docsExpanded, setDocsExpanded] = useState(false);
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null);

  const loadDocuments = async () => {
    if (!botId) return;
    try {
      const docs = await api<KnowledgeDocument[]>(`/api/bot/${botId}/documents`);
      setDocuments(docs);
    } catch {
      setDocuments([]);
    }
  };

  const loadSources = async () => {
    if (!botId) return;
    try {
      const data = await api<SourceData[]>(`/api/bot/${botId}/sources`);
      setSources(data);
    } catch {
      setSources([]);
    }
  };

  useEffect(() => {
    loadDocuments();
    loadSources();
  }, [botId]);

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

  const handleDeleteSource = (sourceId: string) => {
    setDeleteSourceId(sourceId);
  };

  const confirmDeleteSource = async () => {
    if (!deleteSourceId) return;
    const sourceId = deleteSourceId;
    setDeleteSourceId(null);
    try {
      await api(`/api/bot/${botId}/sources/${sourceId}?delete_documents=true`, {
        method: "DELETE",
      });
      await loadSources();
      await loadDocuments();
    } catch {
      // silently fail
    }
  };

  const handleRediscover = (_sourceId: string) => {
    setAddMode("web");
  };

  const handleSourceDone = async () => {
    setAddMode(null);
    await loadSources();
    await loadDocuments();
  };

  const confidentialityFilter = filter
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // If we're in add-source mode, show the wizard
  if (addMode === "web") {
    return (
      <div className="space-y-6">
        <h3 className="text-base font-semibold">{t("bot.knowledge.title")}</h3>
        <SourceWizardWeb
          botId={botId}
          intents={config.intents}
          onDone={handleSourceDone}
          onCancel={() => setAddMode(null)}
        />
      </div>
    );
  }

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
      </div>

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}

      {/* Sources list */}
      <div className="space-y-3 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">{t("bot.sources.title")}</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setAddMode("web")}>
              <Plus size={14} />
              {t("bot.sources.typeWeb")}
            </Button>
          </div>
        </div>

        {sources.length === 0 && (
          <div className="text-center py-6 text-sm text-gray-400">
            <p>{t("bot.sources.empty")}</p>
            <p className="text-xs mt-1">{t("bot.sources.emptyDesc")}</p>
          </div>
        )}

        <div className="space-y-2">
          {sources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              onRediscover={handleRediscover}
              onDelete={handleDeleteSource}
            />
          ))}
        </div>
      </div>

      {/* Document tagging table — collapsible fallback */}
      <div className="space-y-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <button
          className="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
          onClick={() => setDocsExpanded(!docsExpanded)}
        >
          {docsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {t("bot.sources.allDocuments")} ({documents.length})
        </button>

        {docsExpanded && (
          <>
            <DocumentTagTable
              documents={documents}
              intents={config.intents}
              confidentialityFilter={confidentialityFilter}
              botId={botId}
              onUpdated={loadDocuments}
            />
            <CoverageBar intents={config.intents} documents={documents} />
          </>
        )}
      </div>

      <ConfirmDialog
        open={deleteSourceId !== null}
        title={t("bot.sources.deleteSource")}
        message={
          deleteSourceId
            ? (() => {
                const s = sources.find((x) => x.id === deleteSourceId);
                return s && s.document_count > 0
                  ? t("bot.sources.deleteConfirm", { count: s.document_count })
                  : t("bot.sources.deleteSource");
              })()
            : ""
        }
        confirmLabel={t("common.delete")}
        cancelLabel={t("common.cancel")}
        variant="danger"
        onConfirm={confirmDeleteSource}
        onCancel={() => setDeleteSourceId(null)}
      />
    </div>
  );
}
