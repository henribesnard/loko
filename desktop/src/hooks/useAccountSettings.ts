import { useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Profile {
  display_name: string;
  email: string;
  email_verified_at: string | null;
  language: string;
  timezone: string;
  created_at: string;
  role: string;
  org_name: string;
}

export interface Session {
  id: string;
  created_at: string;
  user_agent: string;
  ip_address: string;
  is_current: boolean;
}

export interface Member {
  id: string;
  account_id: string;
  user_id: string;
  role: string;
  created_at: string;
  email: string;
  display_name: string;
  email_verified_at: string | null;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  invited_by: string;
  created_at: string;
  expires_at: string;
}

export interface TeamData {
  members: Member[];
  invitations: Invitation[];
}

export interface UsageData {
  plan: string;
  quotas: {
    bots: { used: number; limit: number };
    intents_per_bot: { limit: number };
    documents: { limit: number };
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAccountSettings() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [team, setTeam] = useState<TeamData | null>(null);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- Profile ---

  const loadProfile = useCallback(async () => {
    try {
      const data = await api<Profile>("/api/account/profile");
      setProfile(data);
    } catch (e: any) {
      setError(e.message || "Failed to load profile");
    }
  }, []);

  const updateProfile = useCallback(
    async (updates: Partial<Pick<Profile, "display_name" | "language" | "timezone">>) => {
      await api("/api/account/profile", { method: "PATCH", body: JSON.stringify(updates) });
      await loadProfile();
    },
    [loadProfile],
  );

  const resendVerification = useCallback(async () => {
    await api("/api/account/profile/resend-verification", { method: "POST" });
  }, []);

  // --- Security ---

  const loadSessions = useCallback(async () => {
    try {
      const data = await api<Session[]>("/api/account/sessions");
      setSessions(data);
    } catch {
      /* fail-open */
    }
  }, []);

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await api("/api/account/password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      await loadSessions();
    },
    [loadSessions],
  );

  const revokeSession = useCallback(
    async (sessionId: string) => {
      await api(`/api/account/sessions/${sessionId}`, { method: "DELETE" });
      await loadSessions();
    },
    [loadSessions],
  );

  const revokeOtherSessions = useCallback(async () => {
    await api("/api/account/sessions?others=true", { method: "DELETE" });
    await loadSessions();
  }, [loadSessions]);

  // --- Team ---

  const loadTeam = useCallback(async () => {
    try {
      const data = await api<TeamData>("/api/account/team");
      setTeam(data);
    } catch {
      /* viewer fallback — may not have access */
    }
  }, []);

  const inviteMembers = useCallback(
    async (emails: string[], role: string) => {
      const result = await api<{ results: Array<{ email: string; status: string }> }>(
        "/api/account/team/invite",
        { method: "POST", body: JSON.stringify({ emails, role }) },
      );
      await loadTeam();
      return result.results;
    },
    [loadTeam],
  );

  const updateMemberRole = useCallback(
    async (userId: string, role: string) => {
      await api(`/api/account/team/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      await loadTeam();
    },
    [loadTeam],
  );

  const removeMember = useCallback(
    async (userId: string) => {
      await api(`/api/account/team/${userId}`, { method: "DELETE" });
      await loadTeam();
    },
    [loadTeam],
  );

  const cancelInvitation = useCallback(
    async (invitationId: string) => {
      await api(`/api/account/team/invite/${invitationId}`, { method: "DELETE" });
      await loadTeam();
    },
    [loadTeam],
  );

  const resendInvitation = useCallback(
    async (invitationId: string) => {
      await api(`/api/account/team/invite/${invitationId}/resend`, { method: "POST" });
    },
    [],
  );

  // --- Usage ---

  const loadUsage = useCallback(async () => {
    try {
      const data = await api<UsageData>("/api/account/usage");
      setUsage(data);
    } catch {
      /* fail-open */
    }
  }, []);

  // --- RGPD ---

  const exportData = useCallback(async () => {
    const data = await api("/api/account/export", { method: "POST" });
    return data;
  }, []);

  const deleteAccount = useCallback(async (password: string) => {
    await api("/api/account", {
      method: "DELETE",
      body: JSON.stringify({ password, confirm: "SUPPRIMER" }),
    });
  }, []);

  // --- Init ---

  useEffect(() => {
    setLoading(true);
    Promise.all([loadProfile(), loadSessions(), loadTeam(), loadUsage()])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [loadProfile, loadSessions, loadTeam, loadUsage]);

  return {
    // Profile
    profile,
    updateProfile,
    resendVerification,
    // Security
    sessions,
    changePassword,
    revokeSession,
    revokeOtherSessions,
    // Team
    team,
    inviteMembers,
    updateMemberRole,
    removeMember,
    cancelInvitation,
    resendInvitation,
    // Usage
    usage,
    // RGPD
    exportData,
    deleteAccount,
    // State
    loading,
    error,
  };
}
