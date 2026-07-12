import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LokoLockup } from "@/components/ui/LokoLockup";

interface LoginPageProps {
  onLogin: (email: string, password: string) => Promise<string | null>;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError(null);

    const loginError = await onLogin(email.trim(), password);
    if (loginError === null) {
      // F3: honour ?next= redirect after login
      const next = searchParams.get("next") || "/bot";
      const safe = next.startsWith("/") && !next.startsWith("//") ? next : "/bot";
      navigate(safe, { replace: true });
    } else {
      setError(loginError === "auth.error" ? t("auth.error") : loginError);
    }
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

          {error && (
            <p className="text-xs" style={{ color: "var(--error-fg)" }}>{error}</p>
          )}

          <Button
            type="submit"
            size="md"
            className="w-full"
            disabled={loading || !email.trim() || !password}
          >
            {t("auth.login")}
          </Button>
        </form>

        {/* Footer links */}
        <div className="mt-6 text-center space-y-2">
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
        </div>
      </div>
    </div>
  );
}
