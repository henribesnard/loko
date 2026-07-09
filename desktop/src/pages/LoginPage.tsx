import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LokoLockup } from "@/components/ui/LokoLockup";

interface LoginPageProps {
  onLogin: (emailOrToken: string, password?: string) => Promise<boolean>;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"email" | "token">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    let ok: boolean;
    if (mode === "email") {
      if (!email.trim() || !password) return setLoading(false);
      ok = await onLogin(email.trim(), password);
    } else {
      if (!token.trim()) return setLoading(false);
      ok = await onLogin(token.trim());
    }

    if (!ok) setError(t("auth.error"));
    setLoading(false);
  };

  return (
    <div
      className="flex h-screen items-center justify-center"
      style={{ background: "var(--surface-page)" }}
    >
      <div
        className="w-full max-w-sm px-8 py-10"
        style={{
          background: "var(--surface-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        {/* Logo */}
        <div className="flex items-center justify-center mb-8">
          <LokoLockup height={32} />
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "email" ? (
            <>
              <Input
                type="email"
                label={t("auth.emailLabel")}
                placeholder={t("auth.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
              <Input
                type="password"
                label={t("auth.passwordLabel")}
                placeholder={t("auth.passwordPlaceholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </>
          ) : (
            <Input
              type="password"
              label={t("auth.tokenLabel")}
              placeholder={t("auth.tokenPlaceholder")}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoFocus
            />
          )}

          {error && (
            <p className="text-xs" style={{ color: "var(--error-fg)" }}>{error}</p>
          )}

          <Button
            type="submit"
            size="md"
            className="w-full"
            disabled={
              loading ||
              (mode === "email" ? !email.trim() || !password : !token.trim())
            }
          >
            {t("auth.login")}
          </Button>
        </form>

        {/* Footer links */}
        <div className="mt-6 text-center space-y-2">
          {mode === "email" && (
            <>
              <Link
                to="/signup"
                className="block text-xs font-medium"
                style={{ color: "var(--text-link)" }}
              >
                {t("auth.createAccount")}
              </Link>
              <Link
                to="/reset"
                className="block text-xs"
                style={{ color: "var(--text-tertiary)" }}
              >
                {t("auth.forgotPassword")}
              </Link>
            </>
          )}
          <button
            type="button"
            onClick={() => setMode(mode === "email" ? "token" : "email")}
            className="text-xs"
            style={{ color: "var(--text-tertiary)" }}
          >
            {mode === "email" ? t("auth.useToken") : t("auth.useEmail")}
          </button>
        </div>
      </div>
    </div>
  );
}
