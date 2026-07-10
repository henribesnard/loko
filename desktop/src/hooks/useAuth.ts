/**
 * LOKO — Authentication hook.
 *
 * T3: Session cookie is the sole auth mechanism for regular users.
 * Legacy admin token login removed — ops-only token flow is on /ops page.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

export interface UserInfo {
  id: string;
  email: string;
  role: string;
  email_verified: boolean;
}

export interface AccountInfo {
  id: string;
  org_name: string;
  plan: string;
}

interface AuthState {
  authenticated: boolean;
  loading: boolean;
  error: string | null;
  user: UserInfo | null;
  account: AccountInfo | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

export function useAuth(): AuthState {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [account, setAccount] = useState<AccountInfo | null>(null);

  // Check existing session on mount
  useEffect(() => {
    checkSession();
  }, []);

  async function checkSession() {
    try {
      const data = await api<{ user: UserInfo; account: AccountInfo }>("/api/auth/me");
      setUser(data.user);
      setAccount(data.account);
      setAuthenticated(true);
    } catch {
      // No valid session — user must log in
    }
    setLoading(false);
  }

  const login = useCallback(async (email: string, password: string): Promise<boolean> => {
    setError(null);
    try {
      const data = await api<{ user: UserInfo; account: AccountInfo }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUser(data.user);
      setAccount(data.account);
      setAuthenticated(true);
      return true;
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const body = JSON.parse(err.body);
          setError(body.detail || "auth.error");
        } catch {
          setError("auth.error");
        }
      } else {
        setError("auth.error");
      }
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      // Ignore logout errors
    }
    setUser(null);
    setAccount(null);
    setAuthenticated(false);
    setError(null);
  }, []);

  return { authenticated, loading, error, user, account, login, logout };
}
