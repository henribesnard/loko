/**
 * LOKO — Hook for bot configuration CRUD.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  BotConfig,
  BotListItem,
  Channel,
  BotLanguage,
  ToneProfile,
  Intent,
  JourneyParams,
  MessageTemplate,
} from "@/types/bot";

export function useBotList() {
  const [bots, setBots] = useState<BotListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<BotListItem[]>("/api/bot/");
      setBots(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load bots");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createBot = useCallback(
    async (name: string, channel: Channel = "both", language: BotLanguage = "fr", tone: ToneProfile = "neutre") => {
      const data = await api<BotConfig>("/api/bot/", {
        method: "POST",
        body: JSON.stringify({ name, channel, language, tone_profile: tone }),
      });
      await refresh();
      return data;
    },
    [refresh],
  );

  const deleteBot = useCallback(
    async (botId: string) => {
      await api(`/api/bot/${botId}`, { method: "DELETE" });
      await refresh();
    },
    [refresh],
  );

  return { bots, loading, error, refresh, createBot, deleteBot };
}

export function useBotConfig(botId: string | undefined) {
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!botId) return;
    setLoading(true);
    setError(null);
    api<BotConfig>(`/api/bot/${botId}`)
      .then(setConfig)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load bot"))
      .finally(() => setLoading(false));
  }, [botId]);

  const updateConfig = useCallback(
    async (updates: Partial<{
      name: string;
      channel: Channel;
      language: BotLanguage;
      tone_profile: ToneProfile;
      intents: Intent[];
      journey: JourneyParams;
      templates: Record<string, MessageTemplate>;
      knowledge_collection: string;
      confidentiality_filter: string[];
    }>) => {
      if (!botId) return;
      setSaving(true);
      try {
        const updated = await api<BotConfig>(`/api/bot/${botId}`, {
          method: "PUT",
          body: JSON.stringify(updates),
        });
        setConfig(updated);
        return updated;
      } finally {
        setSaving(false);
      }
    },
    [botId],
  );

  const publish = useCallback(async () => {
    if (!botId) return;
    const result = await api<{ status: string; bot_id: string }>(
      `/api/bot/${botId}/publish`,
      { method: "POST" },
    );
    // Refresh config to get updated status
    const updated = await api<BotConfig>(`/api/bot/${botId}`);
    setConfig(updated);
    return result;
  }, [botId]);

  return { config, loading, error, saving, updateConfig, publish };
}
