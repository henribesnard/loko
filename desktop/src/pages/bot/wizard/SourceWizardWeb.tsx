import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Loader2,
  Plus,
  Trash2,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { TagMultiSelect, type TagOption } from "./TagMultiSelect";
import { api } from "@/lib/api";

// ---------- Types ----------

interface Intent {
  id: string;
  label: string;
  sub_motifs: { id: string; label: string }[];
}

interface TagRule {
  pattern: string;
  bot_intents: string[];
  bot_sub_motifs: string[];
  confidentiality: string | null;
}

interface DiscoveredDoc {
  doc_id: string;
  url: string;
  title: string;
  content_hash: string;
  content_preview: string;
  bot_intents: string[];
  bot_sub_motifs: string[];
  confidentiality: string;
  tagged: boolean;
}

interface CrawlResponse {
  documents_discovered: number;
  documents_selected: number;
  documents_ingested: number;
  documents_untagged: number;
  untagged_paths: string[];
  documents: DiscoveredDoc[];
  errors: string[];
  ingested: { doc_id: string; url: string; title: string }[];
}

interface SourceWizardWebProps {
  botId: string;
  intents: Intent[];
  onDone: () => void;
  onCancel: () => void;
}

// ---------- Helpers ----------

function buildIntentOptions(intents: Intent[]): TagOption[] {
  const opts: TagOption[] = [];
  for (const i of intents) {
    opts.push({ id: i.id, label: i.label || i.id });
    for (const sm of i.sub_motifs) {
      opts.push({ id: sm.id, label: sm.label || sm.id, group: i.label || i.id });
    }
  }
  return opts;
}

function evaluateTagRules(
  docUrl: string,
  rules: TagRule[],
  defaultTags: TagRule | null,
): { intents: string[]; subMotifs: string[]; conf: string; tagged: boolean } {
  const path = new URL(docUrl).pathname;
  for (const rule of rules) {
    if (globMatch(path, rule.pattern)) {
      return {
        intents: rule.bot_intents,
        subMotifs: rule.bot_sub_motifs,
        conf: rule.confidentiality || "public",
        tagged: rule.bot_intents.length > 0,
      };
    }
  }
  if (defaultTags) {
    return {
      intents: defaultTags.bot_intents,
      subMotifs: defaultTags.bot_sub_motifs,
      conf: defaultTags.confidentiality || "public",
      tagged: defaultTags.bot_intents.length > 0,
    };
  }
  return { intents: [], subMotifs: [], conf: "public", tagged: false };
}

function globMatch(path: string, pattern: string): boolean {
  const re = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${re}$`).test(path);
}

function suggestRulesFromPaths(docs: DiscoveredDoc[]): string[] {
  const dirs = new Set<string>();
  for (const doc of docs) {
    try {
      const path = new URL(doc.url).pathname;
      const parts = path.split("/").filter(Boolean);
      if (parts.length >= 2) {
        dirs.add(`/${parts.slice(0, -1).join("/")}/*`);
      }
    } catch {
      // skip invalid URLs
    }
  }
  return Array.from(dirs).sort();
}

// ---------- Component ----------

export function SourceWizardWeb({
  botId,
  intents,
  onDone,
  onCancel,
}: SourceWizardWebProps) {
  const { t } = useTranslation();
  const intentOptions = useMemo(() => buildIntentOptions(intents), [intents]);

  // Screen state
  const [screen, setScreen] = useState<1 | 2 | 3>(1);

  // Screen 1 state
  const [label, setLabel] = useState("");
  const [startUrl, setStartUrl] = useState("");
  const [docPattern, setDocPattern] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState("");

  // Screen 2 state (set after discovery)
  const [discoveredDocs, setDiscoveredDocs] = useState<DiscoveredDoc[]>([]);
  const [tagRules, setTagRules] = useState<TagRule[]>([]);
  const [defaultTags, setDefaultTags] = useState<TagRule | null>(null);
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  // Screen 3 state
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<CrawlResponse | null>(null);
  const [ingestError, setIngestError] = useState("");
  const [showIngestConfirm, setShowIngestConfirm] = useState(false);


  // ---------- Screen 1: Discover ----------

  const handleDiscover = async () => {
    if (!startUrl.trim()) return;
    setDiscovering(true);
    setDiscoverError("");
    try {
      const result = await api<CrawlResponse>(`/api/bot/${botId}/knowledge/crawl`, {
        method: "POST",
        body: JSON.stringify({
          start_url: startUrl.trim(),
          use_playwright: true,
          follow_iframes: true,
          document_url_patterns: docPattern.trim() ? [docPattern.trim()] : [],
          ingest: false,
        }),
      });
      setDiscoveredDocs(result.documents);
      // Pre-fill tag rules from discovered directory patterns
      const suggestions = suggestRulesFromPaths(result.documents);
      setTagRules(
        suggestions.map((p) => ({
          pattern: p,
          bot_intents: [],
          bot_sub_motifs: [],
          confidentiality: null,
        })),
      );
      setScreen(2);
    } catch (err) {
      setDiscoverError(err instanceof Error ? err.message : "Discovery failed");
    } finally {
      setDiscovering(false);
    }
  };

  // ---------- Screen 2: Preview & Rules ----------

  const previewDocs = useMemo(() => {
    return discoveredDocs.map((doc) => {
      const tags = evaluateTagRules(doc.url, tagRules, defaultTags);
      return { ...doc, ...tags };
    });
  }, [discoveredDocs, tagRules, defaultTags]);

  const taggedCount = previewDocs.filter((d) => d.tagged).length;
  const untaggedCount = previewDocs.length - taggedCount;

  const updateRule = (idx: number, updates: Partial<TagRule>) => {
    setTagRules((prev) => prev.map((r, i) => (i === idx ? { ...r, ...updates } : r)));
  };

  const removeRule = (idx: number) => {
    setTagRules((prev) => prev.filter((_, i) => i !== idx));
  };

  const addRule = () => {
    setTagRules((prev) => [
      ...prev,
      { pattern: "", bot_intents: [], bot_sub_motifs: [], confidentiality: null },
    ]);
  };

  const moveRule = (idx: number, dir: -1 | 1) => {
    setTagRules((prev) => {
      const next = [...prev];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  // ---------- Screen 3: Ingest ----------

  const handleIngest = () => {
    if (untaggedCount > 0) {
      setShowIngestConfirm(true);
      return;
    }
    doIngest();
  };

  const doIngest = async () => {
    setShowIngestConfirm(false);
    setIngesting(true);
    setIngestError("");
    try {
      // 1. Create the source in config
      const source = await api<{ id: string }>(`/api/bot/${botId}/sources`, {
        method: "POST",
        body: JSON.stringify({
          type: "web",
          label: label.trim() || new URL(startUrl).hostname,
          start_url: startUrl.trim(),
          document_url_patterns: docPattern.trim() ? [docPattern.trim()] : [],
          tag_rules: tagRules.filter((r) => r.pattern.trim()),
          default_tags: defaultTags,
        }),
      });

      // 2. Crawl with ingest: true and source_id
      const result = await api<CrawlResponse>(`/api/bot/${botId}/knowledge/crawl`, {
        method: "POST",
        body: JSON.stringify({
          start_url: startUrl.trim(),
          use_playwright: true,
          follow_iframes: true,
          document_url_patterns: docPattern.trim() ? [docPattern.trim()] : [],
          ingest: true,
          source_id: source.id,
          tag_rules: tagRules.filter((r) => r.pattern.trim()),
          default_tags: defaultTags,
        }),
      });
      setIngestResult(result);
      setScreen(3);
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setIngesting(false);
    }
  };

  // ---------- Render ----------

  if (screen === 1) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onCancel}>
            <ArrowLeft size={14} />
            {t("bot.sources.back")}
          </Button>
          <h4 className="text-sm font-semibold">{t("bot.sources.typeWeb")}</h4>
        </div>

        <Input
          placeholder={t("bot.sources.labelPlaceholder")}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Input
          placeholder={t("bot.sources.startUrlPlaceholder")}
          value={startUrl}
          onChange={(e) => setStartUrl(e.target.value)}
        />
        <Input
          placeholder={t("bot.sources.docPatternPlaceholder")}
          value={docPattern}
          onChange={(e) => setDocPattern(e.target.value)}
        />

        <Button
          size="sm"
          onClick={handleDiscover}
          disabled={discovering || !startUrl.trim()}
        >
          {discovering && <Loader2 size={14} className="animate-spin" />}
          {discovering ? t("bot.sources.discovering") : t("bot.sources.discover")}
        </Button>

        {discoverError && (
          <p className="text-xs text-red-600 dark:text-red-400">{discoverError}</p>
        )}
      </div>
    );
  }

  if (screen === 2) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setScreen(1)}>
            <ArrowLeft size={14} />
            {t("bot.sources.back")}
          </Button>
          <h4 className="text-sm font-semibold">{t("bot.sources.preview")}</h4>
        </div>

        {/* Counter */}
        <div className="text-xs font-medium px-3 py-2 rounded bg-gray-50 dark:bg-gray-800">
          {t("bot.sources.previewDocs", {
            total: previewDocs.length,
            tagged: taggedCount,
            untagged: untaggedCount,
          })}
        </div>

        {/* Tag rules editor */}
        <div className="space-y-3">
          <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
            {t("bot.sources.tagRules")}
          </p>
          {tagRules.map((rule, idx) => (
            <div
              key={idx}
              className="flex flex-col gap-2 p-3 rounded border border-gray-200 dark:border-gray-700"
            >
              <div className="flex items-center gap-2">
                <Input
                  className="flex-1 text-xs"
                  placeholder={t("bot.sources.patternPlaceholder")}
                  value={rule.pattern}
                  onChange={(e) => updateRule(idx, { pattern: e.target.value })}
                />
                <div className="flex gap-0.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => moveRule(idx, -1)}
                    disabled={idx === 0}
                  >
                    <ChevronUp size={12} />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => moveRule(idx, 1)}
                    disabled={idx === tagRules.length - 1}
                  >
                    <ChevronDown size={12} />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removeRule(idx)}
                    className="text-red-500"
                  >
                    <Trash2 size={12} />
                  </Button>
                </div>
              </div>
              <TagMultiSelect
                label={t("bot.knowledge.table.intents")}
                options={intentOptions.filter((o) => !o.group)}
                selected={rule.bot_intents}
                onChange={(sel) => updateRule(idx, { bot_intents: sel })}
              />
              <Input
                className="text-xs"
                placeholder={t("bot.sources.confidentiality")}
                value={rule.confidentiality || ""}
                onChange={(e) =>
                  updateRule(idx, {
                    confidentiality: e.target.value || null,
                  })
                }
              />
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={addRule}>
            <Plus size={14} />
            {t("bot.sources.addRule")}
          </Button>

          {/* Default tags */}
          <div className="p-3 rounded border border-dashed border-gray-300 dark:border-gray-600 space-y-2">
            <p className="text-xs font-medium text-gray-500">
              {t("bot.sources.defaultTags")}
            </p>
            <TagMultiSelect
              label={t("bot.knowledge.table.intents")}
              options={intentOptions.filter((o) => !o.group)}
              selected={defaultTags?.bot_intents || []}
              onChange={(sel) =>
                setDefaultTags({
                  pattern: "*",
                  bot_intents: sel,
                  bot_sub_motifs: [],
                  confidentiality: null,
                })
              }
            />
          </div>
        </div>

        {/* Document preview table */}
        <div className="space-y-1 max-h-80 overflow-y-auto">
          {previewDocs.map((doc) => (
            <div
              key={doc.doc_id}
              className={`text-xs rounded p-2 cursor-pointer ${
                doc.tagged
                  ? "bg-white dark:bg-gray-900"
                  : "bg-amber-50 dark:bg-amber-900/20"
              } border border-gray-100 dark:border-gray-800`}
              onClick={() =>
                setExpandedDoc(expandedDoc === doc.doc_id ? null : doc.doc_id)
              }
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{doc.title}</span>
                <span
                  className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded ${
                    doc.tagged
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  }`}
                >
                  {doc.tagged ? t("bot.sources.tagged") : t("bot.sources.untagged")}
                </span>
              </div>
              <p className="text-gray-400 truncate">{new URL(doc.url).pathname}</p>
              {doc.tagged && doc.intents.length > 0 && (
                <div className="flex gap-1 mt-1 flex-wrap">
                  {doc.intents.map((iid) => {
                    const intent = intents.find((i) => i.id === iid);
                    return (
                      <span
                        key={iid}
                        className="text-[10px] px-1 py-0.5 rounded bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                      >
                        {intent?.label || iid}
                      </span>
                    );
                  })}
                </div>
              )}
              {expandedDoc === doc.doc_id && (
                <div className="mt-2 p-2 bg-gray-50 dark:bg-gray-800 rounded text-[11px] text-gray-600 dark:text-gray-300 whitespace-pre-wrap max-h-32 overflow-y-auto">
                  {doc.content_preview}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Ingest button */}
        <div className="flex items-center gap-3 pt-2">
          <Button size="sm" onClick={handleIngest} disabled={ingesting}>
            {ingesting && <Loader2 size={14} className="animate-spin" />}
            {ingesting
              ? t("bot.sources.ingesting")
              : t("bot.sources.ingest", { count: previewDocs.length })}
          </Button>
          {ingestError && (
            <p className="text-xs text-red-600 dark:text-red-400">{ingestError}</p>
          )}
        </div>

        <ConfirmDialog
          open={showIngestConfirm}
          title={t("bot.sources.ingest", { count: previewDocs.length })}
          message={t("bot.sources.ingestConfirm", { untagged: untaggedCount })}
          confirmLabel={t("bot.sources.ingest", { count: previewDocs.length })}
          cancelLabel={t("common.cancel")}
          onConfirm={doIngest}
          onCancel={() => setShowIngestConfirm(false)}
        />
      </div>
    );
  }

  // Screen 3: Summary
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
        <CheckCircle2 size={16} />
        <h4 className="text-sm font-semibold">
          {t("bot.sources.ingest", { count: ingestResult?.documents_ingested || 0 })}
        </h4>
      </div>

      {ingestResult && (
        <div className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
          <p>
            {ingestResult.documents_discovered} {t("bot.sources.discovered")} —{" "}
            {ingestResult.documents_ingested} {t("bot.sources.ingested")}
          </p>
          {ingestResult.documents_untagged > 0 && (
            <p className="flex items-center gap-1 text-amber-600">
              <AlertTriangle size={12} />
              {ingestResult.documents_untagged} {t("bot.sources.untagged")}
            </p>
          )}
          {ingestResult.errors.length > 0 && (
            <p className="text-red-500">
              {ingestResult.errors.length} {t("bot.sources.errors")}
            </p>
          )}
        </div>
      )}

      <Button size="sm" onClick={onDone}>
        OK
      </Button>
    </div>
  );
}
