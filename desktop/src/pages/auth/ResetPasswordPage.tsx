import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LokoLockup } from "@/components/ui/LokoLockup";
import { api, ApiError } from "@/lib/api";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const tokenParam = searchParams.get("token");

  if (tokenParam) {
    return <ResetForm token={tokenParam} />;
  }
  return <RequestResetForm />;
}

function RequestResetForm() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    try {
      await api("/api/auth/request-reset", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
    } catch {
      // Always show success (anti-enumeration)
    }
    setSent(true);
    setLoading(false);
  };

  return (
    <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-page)" }}>
      <div className="w-full max-w-sm px-8 py-10" style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)" }}>
        <div className="flex items-center justify-center mb-8">
          <LokoLockup height={32} />
        </div>

        {sent ? (
          <div className="text-center">
            <h2 className="text-base font-semibold mb-2" style={{ color: "var(--text-primary)" }}>{t("auth.resetEmailSent")}</h2>
            <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>{t("auth.resetEmailSentDesc")}</p>
            <Link to="/login">
              <Button size="md" variant="secondary" className="w-full">{t("auth.backToLogin")}</Button>
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-base font-semibold mb-4" style={{ color: "var(--text-primary)" }}>{t("auth.resetPassword")}</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                type="email"
                label={t("auth.emailLabel")}
                placeholder={t("auth.emailPlaceholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
              />
              <Button type="submit" size="md" className="w-full" disabled={loading || !email.trim()}>
                {t("auth.sendResetLink")}
              </Button>
            </form>
            <div className="mt-4 text-center">
              <Link to="/login" className="text-xs" style={{ color: "var(--text-link)" }}>{t("auth.backToLogin")}</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ResetForm({ token }: { token: string }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setLoading(true);
    setError(null);
    try {
      await api("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const body = JSON.parse(err.body);
          setError(typeof body.detail === "string" ? body.detail : t("auth.resetError"));
        } catch {
          setError(t("auth.resetError"));
        }
      } else {
        setError(t("auth.resetError"));
      }
    }
    setLoading(false);
  };

  if (success) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-page)" }}>
        <div className="w-full max-w-sm px-8 py-10 text-center" style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)" }}>
          <h2 className="text-base font-semibold mb-2" style={{ color: "var(--text-primary)" }}>{t("auth.resetSuccess")}</h2>
          <Link to="/login">
            <Button size="md" className="w-full">{t("auth.backToLogin")}</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-page)" }}>
      <div className="w-full max-w-sm px-8 py-10" style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)" }}>
        <div className="flex items-center justify-center mb-8">
          <LokoLockup height={32} />
        </div>
        <h2 className="text-base font-semibold mb-4" style={{ color: "var(--text-primary)" }}>{t("auth.newPassword")}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="password"
            label={t("auth.passwordLabel")}
            placeholder={t("auth.passwordPlaceholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          {error && <p className="text-xs" style={{ color: "var(--error-fg)" }}>{error}</p>}
          <Button type="submit" size="md" className="w-full" disabled={loading || !password}>
            {t("auth.resetPassword")}
          </Button>
        </form>
      </div>
    </div>
  );
}
