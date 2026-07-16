import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import type {
  AssistantRequest,
  AssistantResponse,
  Proposal,
} from "@/types/bot";

export function useAssistant(botId: string) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(
    async (req: AssistantRequest) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api<AssistantResponse>(
          `/api/bot/${botId}/assistant/ask`,
          {
            method: "POST",
            body: JSON.stringify(req),
          },
        );
        setProposals(res.proposals);
      } catch (e: unknown) {
        if (e && typeof e === "object" && "status" in e) {
          const status = (e as { status: number }).status;
          if (status === 429) {
            setError("quota_exceeded");
          } else if (status === 503) {
            setError("llm_unavailable");
          } else {
            setError(e instanceof Error ? e.message : String(e));
          }
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setLoading(false);
      }
    },
    [botId],
  );

  const accept = useCallback(
    async (items: { intent_id: string; content: string }[]) => {
      setError(null);
      try {
        await api(`/api/bot/${botId}/assistant/accept`, {
          method: "POST",
          body: JSON.stringify({ items }),
        });
        // Mark accepted proposals
        const acceptedContents = new Set(items.map((i) => i.content));
        setProposals((prev) =>
          prev.map((p) =>
            acceptedContents.has(p.content)
              ? { ...p, status: "accepted" as const }
              : p,
          ),
        );
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        throw e;
      }
    },
    [botId],
  );

  const reject = useCallback((proposalId: string) => {
    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId ? { ...p, status: "rejected" as const } : p,
      ),
    );
  }, []);

  const rejectAll = useCallback(() => {
    setProposals((prev) =>
      prev.map((p) =>
        p.status === "pending" ? { ...p, status: "rejected" as const } : p,
      ),
    );
  }, []);

  const clear = useCallback(() => {
    setProposals([]);
    setError(null);
  }, []);

  return { proposals, loading, error, ask, accept, reject, rejectAll, clear };
}
