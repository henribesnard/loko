/**
 * LOKO — Authentication hook.
 *
 * Supports two modes:
 * 1. Session cookie (new): POST /api/auth/login, GET /api/auth/me
 * 2. Admin token (legacy): Bearer token in sessionStorage for ops or when
 *    the backend has LOKO_ADMIN_TOKEN but no user accounts yet.
 */
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  clearAdminToken,
  getAdminToken,
  setAdminToken,
} from "@/lib/api";

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
  login: (emailOrToken: string, password?: string) => Promise<boolean>;
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
    // 1. Try session cookie first (GET /api/auth/me)
    try {
      const data = await api<{ user: UserInfo; account: AccountInfo }>("/api/auth/me");
      setUser(data.user);
      setAccount(data.account);
      setAuthenticated(true);
      setLoading(false);
      return;
    } catch (err) {
      // No valid session cookie — fall through to legacy token
    }

    // 2. Try legacy admin token
    const token = getAdminToken();
    if (token) {
      try {
        await api("/api/bot/");
        setAuthenticated(true);
        setLoading(false);
        return;
      } catch {
        clearAdminToken();
      }
    }

    setLoading(false);
  }

  const login = useCallback(async (emailOrToken: string, password?: string): Promise<boolean> => {
    setError(null);

    if (password) {
      // Session cookie auth (email + password)
      try {
        const data = await api<{ user: UserInfo; account: AccountInfo }>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: emailOrToken, password }),
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
    } else {
      // Legacy admin token auth
      setAdminToken(emailOrToken);
      try {
        await api("/api/bot/");
        setAuthenticated(true);
        return true;
      } catch {
        clearAdminToken();
        setError("auth.error");
        return false;
      }
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      // Ignore logout errors
    }
    clearAdminToken();
    setUser(null);
    setAccount(null);
    setAuthenticated(false);
    setError(null);
  }, []);

  return { authenticated, loading, error, user, account, login, logout };
}
