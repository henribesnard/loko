import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Database, Globe2, Loader2, Tag } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { DocumentTagTable } from "./DocumentTagTable";
import { CoverageBar } from "./CoverageBar";
import type { WizardStepProps } from "../BotWizard";

interface KnowledgeDocument {
  doc_id: string;
  source_url: string;
  source_title: string;
  bot_intents: string[];
  bot_sub_motifs: string[];
  confidentiality: string;
}

interface CrawlResult {
  documents_discovered: number;
  documents_selected: number;
  documents_ingested: number;
  errors: string[];
}

export function BotKnowledge({ botId, config, updateConfig, saving }: WizardStepProps) {
  const { t } = useTranslation();
  const [collection, setCollection] = useState(config.knowledge_collection);
  const [filter, setFilter] = useState(config.confidentiality_filter.join(", "));
  const [crawlUrl, setCrawlUrl] = useState("");
  const [docPattern, setDocPattern] = useState("");
  const [crawling, setCrawling] = useState(false);
  const [crawlResult, setCrawlResult] = useState<CrawlResult | null>(null);
  const [crawlError, setCrawlError] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [dirty, setDirty] = useState(false);

  const loadDocuments = async () => {
    if (!botId) return;
    try {
      const docs = await api<KnowledgeDocument[]>(`/api/bot/${botId}/documents`);
      setDocuments(docs);
    } catch {
      setDocuments([]);
    }
  };

  useEffect(() => {
    loadDocuments();
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

  const handleCrawl = async () => {
    if (!botId || !crawlUrl.trim()) return;
    setCrawling(true);
    setCrawlError("");
    setCrawlResult(null);
    try {
      const result = await api<CrawlResult>(`/api/bot/${botId}/knowledge/crawl`, {
        method: "POST",
        body: JSON.stringify({
          start_url: crawlUrl.trim(),
          use_playwright: true,
          follow_iframes: true,
          document_url_patterns: docPattern.trim() ? [docPattern.trim()] : [],
          ingest: true,
        }),
      });
      setCrawlResult(result);
      await loadDocuments();
    } catch (err) {
      setCrawlError(err instanceof Error ? err.message : "Crawl failed");
    } finally {
      setCrawling(false);
    }
  };

  const confidentialityFilter = filter
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

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
        <p className="text-xs text-gray-400">
          Tags séparés par virgule. Seuls les documents avec ces tags seront utilisés.
        </p>
      </div>

      {dirty && (
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t("bot.wizard.save")}
        </Button>
      )}

      {/* FAQ web crawler */}
      <div className="space-y-3 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <Globe2 size={14} />
          Connecteur FAQ web
        </div>
        <Input
          placeholder="https://exemple.com/aide/index.html"
          value={crawlUrl}
          onChange={(e) => setCrawlUrl(e.target.value)}
        />
        <Input
          placeholder="Filtre URL documents, ex: /articles/"
          value={docPattern}
          onChange={(e) => setDocPattern(e.target.value)}
        />
        <Button size="sm" onClick={handleCrawl} disabled={crawling || !crawlUrl.trim()}>
          {crawling && <Loader2 size={14} className="animate-spin" />}
          Crawler et ingerer
        </Button>
        {crawlError && (
          <p className="text-xs text-red-600 dark:text-red-400">{crawlError}</p>
        )}
        {crawlResult && (
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {crawlResult.documents_ingested} document(s) ingere(s) sur {crawlResult.documents_selected} selectionne(s)
            {crawlResult.errors.length > 0 && ` - ${crawlResult.errors.length} erreur(s)`}
          </div>
        )}
      </div>

      {/* Document tagging table */}
      <div className="space-y-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
          {t("bot.knowledge.tagging")} ({documents.length})
        </p>

        <DocumentTagTable
          documents={documents}
          intents={config.intents}
          confidentialityFilter={confidentialityFilter}
          botId={botId}
          onUpdated={loadDocuments}
        />

        <CoverageBar intents={config.intents} documents={documents} />
      </div>
    </div>
  );
}
