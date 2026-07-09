import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Bot, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useBotList } from "@/hooks/useBotConfig";

export function BotList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { bots, loading, error: listError, createBot, deleteBot } = useBotList();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const bot = await createBot(newName.trim());
      setShowCreate(false);
      setNewName("");
      navigate(`/bot/${bot.bot_id}/wizard`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, botId: string) => {
    e.stopPropagation();
    if (!confirm(t("bot.deleteConfirm"))) return;
    await deleteBot(botId);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "var(--tracking-tight)" }}>{t("nav.bots")}</h1>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            {t("bot.create")}
          </Button>
        </div>

        {/* List error */}
        {listError && (
          <div
            className="mb-4 p-3 text-sm"
            style={{
              borderRadius: "var(--radius-sm)",
              background: "var(--error-bg)",
              color: "var(--error-fg)",
              border: "1px solid var(--error-border)",
            }}
          >
            {listError}
          </div>
        )}

        {/* Create form */}
        {showCreate && (
          <div
            className="mb-6 p-4"
            style={{
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border-default)",
              background: "var(--surface-card)",
            }}
          >
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder={t("bot.project.namePlaceholder")}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  autoFocus
                />
              </div>
              <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim()}>
                {t("common.save")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowCreate(false);
                  setNewName("");
                  setCreateError(null);
                }}
              >
                {t("common.cancel")}
              </Button>
            </div>
            {createError && (
              <p className="mt-2 text-xs" style={{ color: "var(--error-fg)" }}>{createError}</p>
            )}
          </div>
        )}

        {/* Bot list */}
        {bots.length === 0 ? (
          <div className="text-center py-16">
            <Bot size={40} className="mx-auto mb-3" style={{ color: "var(--text-disabled)" }} />
            <p className="text-sm font-medium" style={{ color: "var(--text-tertiary)" }}>{t("bot.noBot")}</p>
            <p className="text-xs mt-1" style={{ color: "var(--text-disabled)" }}>{t("bot.noBotDesc")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {bots.map((bot) => (
              <div
                key={bot.bot_id}
                onClick={() => navigate(`/bot/${bot.bot_id}/wizard`)}
                className="flex items-center justify-between p-4 cursor-pointer transition-colors"
                style={{
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border-subtle)",
                  background: "var(--surface-card)",
                }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 flex items-center justify-center"
                    style={{
                      borderRadius: "var(--radius-sm)",
                      background: "var(--brand-primary-tint)",
                    }}
                  >
                    <Bot size={16} style={{ color: "var(--brand-primary)" }} />
                  </div>
                  <div>
                    <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{bot.name}</p>
                    <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                      {bot.status === "published"
                        ? t("bot.status.published")
                        : t("bot.status.draft")}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, bot.bot_id)}
                  className="p-1.5 rounded transition-colors hover:text-red-500"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
