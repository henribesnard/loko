import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Check, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { TagMultiSelect } from "./TagMultiSelect";
import type { TagOption } from "./TagMultiSelect";
import { cn } from "@/lib/cn";
import { api } from "@/lib/api";
import type { Intent } from "@/types/bot";

interface KnowledgeDocument {
  doc_id: string;
  source_url: string;
  source_title: string;
  bot_intents: string[];
  bot_sub_motifs: string[];
  confidentiality: string;
}

interface DocumentTagTableProps {
  documents: KnowledgeDocument[];
  intents: Intent[];
  confidentialityFilter: string[];
  botId: string;
  onUpdated: () => void;
}

const PAGE_SIZE = 50;

export function DocumentTagTable({
  documents,
  intents,
  confidentialityFilter,
  botId,
  onUpdated,
}: DocumentTagTableProps) {
  const { t } = useTranslation();

  // Selection
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Bulk action state
  const [bulkIntents, setBulkIntents] = useState<string[]>([]);
  const [bulkSubMotifs, setBulkSubMotifs] = useState<string[]>([]);
  const [bulkMode, setBulkMode] = useState<"replace" | "add">("replace");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Inline editing
  const [editingDoc, setEditingDoc] = useState<string | null>(null);
  const [editIntents, setEditIntents] = useState<string[]>([]);
  const [editSubMotifs, setEditSubMotifs] = useState<string[]>([]);

  // Pagination
  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(documents.length / PAGE_SIZE);
  const pageDocuments = documents.slice(
    page * PAGE_SIZE,
    (page + 1) * PAGE_SIZE,
  );

  // Derived data
  const userIntents = useMemo(
    () => intents.filter((i) => !i.is_system),
    [intents],
  );

  const intentOptions = useMemo<TagOption[]>(
    () => userIntents.map((i) => ({ id: i.id, label: i.label || i.id })),
    [userIntents],
  );

  const getSubMotifOptions = (selectedIntentIds: string[]): TagOption[] => {
    const opts: TagOption[] = [];
    for (const intent of userIntents) {
      if (!selectedIntentIds.includes(intent.id)) continue;
      for (const sm of intent.sub_motifs) {
        opts.push({
          id: sm.id,
          label: sm.label || sm.id,
          group: intent.label || intent.id,
        });
      }
    }
    return opts;
  };

  const bulkSubMotifOptions = useMemo(
    () => getSubMotifOptions(bulkIntents),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bulkIntents, userIntents],
  );

  // ---------------------------------------------------------------------------
  // Selection helpers
  // ---------------------------------------------------------------------------

  const allPageSelected =
    pageDocuments.length > 0 &&
    pageDocuments.every((d) => selected.has(d.doc_id));
  const someSelected = pageDocuments.some((d) => selected.has(d.doc_id));

  const toggleAll = () => {
    const next = new Set(selected);
    if (allPageSelected) {
      for (const d of pageDocuments) next.delete(d.doc_id);
    } else {
      for (const d of pageDocuments) next.add(d.doc_id);
    }
    setSelected(next);
  };

  const selectAllDocuments = () => {
    setSelected(new Set(documents.map((d) => d.doc_id)));
  };

  const toggleOne = (docId: string) => {
    const next = new Set(selected);
    if (next.has(docId)) next.delete(docId);
    else next.add(docId);
    setSelected(next);
  };

  // ---------------------------------------------------------------------------
  // Intent/sub-motif coherence: removing an intent cleans its sub-motifs
  // ---------------------------------------------------------------------------

  const cleanSubMotifs = (intentIds: string[], smIds: string[]) => {
    const validSmIds = new Set<string>();
    for (const intent of userIntents) {
      if (intentIds.includes(intent.id)) {
        for (const sm of intent.sub_motifs) validSmIds.add(sm.id);
      }
    }
    return smIds.filter((id) => validSmIds.has(id));
  };

  const handleBulkIntentsChange = (ids: string[]) => {
    setBulkIntents(ids);
    setBulkSubMotifs((prev) => cleanSubMotifs(ids, prev));
  };

  // ---------------------------------------------------------------------------
  // Bulk apply
  // ---------------------------------------------------------------------------

  const handleBulkApply = async () => {
    const selectedDocs = documents.filter((d) => selected.has(d.doc_id));
    if (selectedDocs.length === 0) return;

    setPending(true);
    setStatus(null);

    try {
      if (bulkMode === "replace") {
        await api(`/api/bot/${botId}/documents/tags`, {
          method: "PATCH",
          body: JSON.stringify({
            doc_ids: selectedDocs.map((d) => d.doc_id),
            bot_intents: bulkIntents,
            bot_sub_motifs: bulkSubMotifs,
          }),
        });
      } else {
        // Add mode: compute union per document, group by identical result
        const groups = new Map<string, string[]>();
        for (const doc of selectedDocs) {
          const mergedIntents = [
            ...new Set([...doc.bot_intents, ...bulkIntents]),
          ];
          const mergedSm = [
            ...new Set([...doc.bot_sub_motifs, ...bulkSubMotifs]),
          ];
          const key = JSON.stringify({
            bot_intents: mergedIntents.sort(),
            bot_sub_motifs: mergedSm.sort(),
          });
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key)!.push(doc.doc_id);
        }
        let applied = 0;
        for (const [key, docIds] of groups) {
          try {
            const payload = JSON.parse(key);
            await api(`/api/bot/${botId}/documents/tags`, {
              method: "PATCH",
              body: JSON.stringify({ doc_ids: docIds, ...payload }),
            });
            applied++;
          } catch (err) {
            setStatus({
              type: "error",
              message: `${applied}/${groups.size} ${t("bot.knowledge.table.groupsApplied")} — ${err instanceof Error ? err.message : "Error"}`,
            });
            setPending(false);
            onUpdated();
            return;
          }
        }
      }

      setStatus({
        type: "success",
        message: t("bot.knowledge.table.updated", {
          count: selectedDocs.length,
        }),
      });
      setBulkIntents([]);
      setBulkSubMotifs([]);
      onUpdated();
    } catch (err) {
      setStatus({
        type: "error",
        message: err instanceof Error ? err.message : "Error",
      });
    } finally {
      setPending(false);
    }
  };

  const handleBulkCancel = () => {
    setSelected(new Set());
    setBulkIntents([]);
    setBulkSubMotifs([]);
  };

  // ---------------------------------------------------------------------------
  // Inline tag removal (chip ×)
  // ---------------------------------------------------------------------------

  const handleRemoveTag = async (
    doc: KnowledgeDocument,
    field: "bot_intents" | "bot_sub_motifs",
    tagId: string,
  ) => {
    let newIntents =
      field === "bot_intents"
        ? doc.bot_intents.filter((id) => id !== tagId)
        : [...doc.bot_intents];
    let newSm =
      field === "bot_sub_motifs"
        ? doc.bot_sub_motifs.filter((id) => id !== tagId)
        : [...doc.bot_sub_motifs];

    // If removing an intent, also remove its sub-motifs
    if (field === "bot_intents") {
      newSm = cleanSubMotifs(newIntents, newSm);
    }

    try {
      await api(`/api/bot/${botId}/documents/tags`, {
        method: "PATCH",
        body: JSON.stringify({
          doc_ids: [doc.doc_id],
          bot_intents: newIntents,
          bot_sub_motifs: newSm,
        }),
      });
      onUpdated();
    } catch {
      // Will be visible on next refresh
    }
  };

  // ---------------------------------------------------------------------------
  // Inline editing (click on cell)
  // ---------------------------------------------------------------------------

  const startInlineEdit = (doc: KnowledgeDocument) => {
    setEditingDoc(doc.doc_id);
    setEditIntents([...doc.bot_intents]);
    setEditSubMotifs([...doc.bot_sub_motifs]);
  };

  const handleInlineIntentsChange = (ids: string[]) => {
    setEditIntents(ids);
    setEditSubMotifs((prev) => cleanSubMotifs(ids, prev));
  };

  const saveInlineEdit = async () => {
    if (!editingDoc) return;
    try {
      await api(`/api/bot/${botId}/documents/tags`, {
        method: "PATCH",
        body: JSON.stringify({
          doc_ids: [editingDoc],
          bot_intents: editIntents,
          bot_sub_motifs: editSubMotifs,
        }),
      });
      setEditingDoc(null);
      onUpdated();
    } catch {
      // Keep editing state open on error
    }
  };

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const isExcluded = (doc: KnowledgeDocument) => {
    if (confidentialityFilter.length === 0) return false;
    return !confidentialityFilter.includes(doc.confidentiality);
  };

  const intentLabel = (id: string) => {
    const intent = userIntents.find((i) => i.id === id);
    return intent ? intent.label || intent.id : id;
  };

  const smLabel = (id: string) => {
    for (const intent of userIntents) {
      const sm = intent.sub_motifs.find((s) => s.id === id);
      if (sm) return sm.label || sm.id;
    }
    return id;
  };

  const isKnownIntent = (id: string) => userIntents.some((i) => i.id === id);
  const isKnownSm = (id: string) =>
    userIntents.some((i) => i.sub_motifs.some((s) => s.id === id));

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (documents.length === 0) return null;

  return (
    <div className="space-y-3">
      {/* Status feedback */}
      {status && (
        <div
          className={cn(
            "px-3 py-2 rounded-lg text-xs flex items-center gap-2",
            status.type === "success" &&
              "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300",
            status.type === "error" &&
              "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300",
          )}
          aria-live="polite"
        >
          {status.type === "error" && <AlertCircle size={14} />}
          {status.message}
          <button
            onClick={() => setStatus(null)}
            className="ml-auto p-0.5 rounded hover:bg-black/10"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div
          className="sticky top-0 z-10 flex flex-wrap items-center gap-2 px-3 py-2 rounded-lg text-xs"
          style={{
            background: "var(--surface-sunken)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <span className="font-medium text-[var(--text-secondary)]">
            {t("bot.knowledge.table.selected", { count: selected.size })}
          </span>

          {/* Select all N documents (Gmail pattern) */}
          {totalPages > 1 &&
            allPageSelected &&
            selected.size < documents.length && (
              <button
                onClick={selectAllDocuments}
                className="text-[var(--text-link)] underline"
              >
                {t("bot.knowledge.table.selectAllDocs", {
                  count: documents.length,
                })}
              </button>
            )}

          <TagMultiSelect
            label={t("bot.knowledge.table.intents")}
            options={intentOptions}
            selected={bulkIntents}
            onChange={handleBulkIntentsChange}
          />
          <TagMultiSelect
            label={t("bot.knowledge.table.subMotifs")}
            options={bulkSubMotifOptions}
            selected={bulkSubMotifs}
            onChange={setBulkSubMotifs}
            disabled={bulkIntents.length === 0}
          />

          <label className="inline-flex items-center gap-1 cursor-pointer text-[var(--text-tertiary)]">
            <input
              type="radio"
              name="bulkMode"
              checked={bulkMode === "replace"}
              onChange={() => setBulkMode("replace")}
              className="accent-[var(--brand-primary)]"
            />
            {t("bot.knowledge.table.modeReplace")}
          </label>
          <label className="inline-flex items-center gap-1 cursor-pointer text-[var(--text-tertiary)]">
            <input
              type="radio"
              name="bulkMode"
              checked={bulkMode === "add"}
              onChange={() => setBulkMode("add")}
              className="accent-[var(--brand-primary)]"
            />
            {t("bot.knowledge.table.modeAdd")}
          </label>

          <Button
            size="sm"
            onClick={handleBulkApply}
            disabled={
              pending ||
              (bulkIntents.length === 0 && bulkSubMotifs.length === 0)
            }
          >
            {pending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Check size={12} />
            )}
            {t("bot.knowledge.table.apply")}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleBulkCancel}>
            {t("bot.knowledge.table.cancel")}
          </Button>
        </div>
      )}

      {/* Table */}
      <div
        className="overflow-x-auto rounded-lg"
        style={{ border: "1px solid var(--border-subtle)" }}
      >
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--surface-sunken)" }}>
              <th className="w-8 px-2 py-2 text-left">
                <input
                  type="checkbox"
                  checked={allPageSelected}
                  ref={(el) => {
                    if (el)
                      el.indeterminate = someSelected && !allPageSelected;
                  }}
                  onChange={toggleAll}
                  aria-checked={
                    allPageSelected
                      ? "true"
                      : someSelected
                        ? "mixed"
                        : "false"
                  }
                  aria-label={t("bot.knowledge.table.selectAll")}
                  className="accent-[var(--brand-primary)]"
                />
              </th>
              <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">
                Document
              </th>
              <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">
                {t("bot.knowledge.table.intents")}
              </th>
              <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">
                {t("bot.knowledge.table.subMotifs")}
              </th>
              <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">
                {t("bot.knowledge.table.confidentiality")}
              </th>
            </tr>
          </thead>
          <tbody>
            {pageDocuments.map((doc) => {
              const excluded = isExcluded(doc);
              const isEditing = editingDoc === doc.doc_id;

              return (
                <tr
                  key={doc.doc_id}
                  className={cn(
                    "border-t transition-colors",
                    excluded && "opacity-50",
                  )}
                  style={{ borderColor: "var(--border-subtle)" }}
                  title={
                    excluded
                      ? t("bot.knowledge.table.excludedTooltip")
                      : undefined
                  }
                >
                  {/* Checkbox */}
                  <td className="px-2 py-2 align-top">
                    <input
                      type="checkbox"
                      checked={selected.has(doc.doc_id)}
                      onChange={() => toggleOne(doc.doc_id)}
                      className="accent-[var(--brand-primary)]"
                    />
                  </td>

                  {/* Document title / URL */}
                  <td className="px-3 py-2 align-top">
                    <p className="font-medium text-[var(--text-primary)] truncate max-w-[220px]">
                      {doc.source_title || doc.source_url}
                    </p>
                    <p className="text-[var(--text-tertiary)] truncate max-w-[220px]">
                      {doc.source_url}
                    </p>
                  </td>

                  {/* Intents column */}
                  <td className="px-3 py-2 align-top">
                    {isEditing ? (
                      <div className="flex items-center gap-1">
                        <TagMultiSelect
                          label={t("bot.knowledge.table.intents")}
                          options={intentOptions}
                          selected={editIntents}
                          onChange={handleInlineIntentsChange}
                        />
                      </div>
                    ) : (
                      <div
                        className="flex flex-wrap gap-1 cursor-pointer min-h-[24px]"
                        onClick={() => startInlineEdit(doc)}
                      >
                        {doc.bot_intents.length === 0 && (
                          <span className="text-[var(--text-tertiary)]">
                            {t("bot.knowledge.table.noTags")}
                          </span>
                        )}
                        {doc.bot_intents.map((id) => (
                          <span
                            key={id}
                            className={cn(
                              "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px]",
                              isKnownIntent(id)
                                ? "bg-[var(--brand-primary-tint)] text-[var(--text-primary)]"
                                : "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400 line-through",
                            )}
                          >
                            {isKnownIntent(id)
                              ? intentLabel(id)
                              : `${id} (${t("bot.knowledge.table.deletedIntent")})`}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemoveTag(doc, "bot_intents", id);
                              }}
                              className="hover:text-[var(--error-fg)]"
                              aria-label={`Remove ${intentLabel(id)}`}
                            >
                              <X size={10} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Sub-motifs column */}
                  <td className="px-3 py-2 align-top">
                    {isEditing ? (
                      <div className="flex items-center gap-1">
                        <TagMultiSelect
                          label={t("bot.knowledge.table.subMotifs")}
                          options={getSubMotifOptions(editIntents)}
                          selected={editSubMotifs}
                          onChange={setEditSubMotifs}
                          disabled={editIntents.length === 0}
                        />
                        <Button size="sm" onClick={saveInlineEdit}>
                          <Check size={10} />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingDoc(null)}
                        >
                          <X size={10} />
                        </Button>
                      </div>
                    ) : (
                      <div
                        className="flex flex-wrap gap-1 cursor-pointer min-h-[24px]"
                        onClick={() => startInlineEdit(doc)}
                      >
                        {doc.bot_sub_motifs.length === 0 && (
                          <span className="text-[var(--text-tertiary)]">
                            {t("bot.knowledge.table.noTags")}
                          </span>
                        )}
                        {doc.bot_sub_motifs.map((id) => (
                          <span
                            key={id}
                            className={cn(
                              "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px]",
                              isKnownSm(id)
                                ? "bg-[var(--brand-primary-tint)] text-[var(--text-primary)]"
                                : "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400 line-through",
                            )}
                          >
                            {isKnownSm(id)
                              ? smLabel(id)
                              : `${id} (${t("bot.knowledge.table.deletedIntent")})`}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemoveTag(doc, "bot_sub_motifs", id);
                              }}
                              className="hover:text-[var(--error-fg)]"
                              aria-label={`Remove ${smLabel(id)}`}
                            >
                              <X size={10} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Confidentiality */}
                  <td className="px-3 py-2 align-top text-[var(--text-tertiary)]">
                    {doc.confidentiality || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 text-xs text-[var(--text-secondary)]">
          <Button
            size="sm"
            variant="ghost"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            ←
          </Button>
          <span>
            {page + 1} / {totalPages}
          </span>
          <Button
            size="sm"
            variant="ghost"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            →
          </Button>
        </div>
      )}
    </div>
  );
}
