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
  const { bots, loading, createBot, deleteBot } = useBotList();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const bot = await createBot(newName.trim());
      setShowCreate(false);
      setNewName("");
      navigate(`/bot/${bot.bot_id}/wizard`);
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
        <p className="text-sm text-gray-500">{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-semibold">{t("nav.bots")}</h1>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} />
            {t("bot.create")}
          </Button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="mb-6 p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
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
                }}
              >
                {t("common.cancel")}
              </Button>
            </div>
          </div>
        )}

        {/* Bot list */}
        {bots.length === 0 ? (
          <div className="text-center py-16">
            <Bot size={40} className="mx-auto mb-3 text-gray-300 dark:text-gray-600" />
            <p className="text-sm font-medium text-gray-500">{t("bot.noBot")}</p>
            <p className="text-xs text-gray-400 mt-1">{t("bot.noBotDesc")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {bots.map((bot) => (
              <div
                key={bot.bot_id}
                onClick={() => navigate(`/bot/${bot.bot_id}/wizard`)}
                className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-brand-300 dark:hover:border-brand-700 cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center">
                    <Bot size={16} className="text-brand-600 dark:text-brand-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{bot.name}</p>
                    <p className="text-xs text-gray-400">
                      {bot.status === "published"
                        ? t("bot.status.published")
                        : t("bot.status.draft")}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, bot.bot_id)}
                  className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
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
