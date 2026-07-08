/**
 * LOKO — Admin authentication hook.
 *
 * Manages admin token in sessionStorage and validates it against the API.
 */
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  clearAdminToken,
  getAdminToken,
  setAdminToken,
} from "@/lib/api";

interface AuthState {
  authenticated: boolean;
  loading: boolean;
  error: string | null;
  login: (token: string) => Promise<boolean>;
  logout: () => void;
}

async function validateToken(): Promise<boolean> {
  try {
    await api("/api/bot/");
    return true;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return false;
    // Network error or other issue — assume valid token, let the app handle it
    return true;
  }
}

export function useAuth(): AuthState {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Check existing token on mount
  useEffect(() => {
    const token = getAdminToken();
    if (!token) {
      setLoading(false);
      return;
    }
    validateToken().then((valid) => {
      setAuthenticated(valid);
      if (!valid) clearAdminToken();
      setLoading(false);
    });
  }, []);

  const login = useCallback(async (token: string): Promise<boolean> => {
    setError(null);
    setAdminToken(token);
    try {
      const valid = await validateToken();
      if (valid) {
        setAuthenticated(true);
        return true;
      }
      clearAdminToken();
      setError("auth.error");
      return false;
    } catch {
      clearAdminToken();
      setError("auth.error");
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    clearAdminToken();
    setAuthenticated(false);
    setError(null);
  }, []);

  return { authenticated, loading, error, login, logout };
}
