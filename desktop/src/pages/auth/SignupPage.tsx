import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LokoLockup } from "@/components/ui/LokoLockup";
import { api, ApiError } from "@/lib/api";

export function SignupPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password || !orgName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
          org_name: orgName.trim(),
          accept_terms: acceptTerms,
        }),
      });
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const body = JSON.parse(err.body);
          const detail = body.detail;
          if (typeof detail === "string") {
            setError(detail);
          } else if (Array.isArray(detail) && detail.length > 0) {
            // Pydantic 422 validation: extract first human-readable msg
            setError(detail.map((e: { msg?: string }) => e.msg || "").filter(Boolean).join(". ") || t("auth.signupError"));
          } else {
            setError(t("auth.signupError"));
          }
        } catch {
          setError(t("auth.signupError"));
        }
      } else {
        setError(t("auth.signupError"));
      }
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-page)" }}>
        <div className="w-full max-w-sm px-8 py-10 text-center" style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)" }}>
          <LokoLockup height={28} className="mx-auto mb-6" />
          <h2 className="text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>{t("auth.signupSuccess")}</h2>
          <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>{t("auth.verifyEmailSent")}</p>
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

        <h2 className="text-base font-semibold mb-4" style={{ color: "var(--text-primary)" }}>{t("auth.signup")}</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="text"
            label={t("auth.orgNameLabel")}
            placeholder={t("auth.orgNamePlaceholder")}
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            autoFocus
          />
          <Input
            type="email"
            label={t("auth.emailLabel")}
            placeholder={t("auth.emailPlaceholder")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <div>
            <Input
              type="password"
              label={t("auth.passwordLabel")}
              placeholder={t("auth.passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={12}
            />
            <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>{t("auth.passwordHint")}</p>
          </div>

          <label className="flex items-start gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <input
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              {t("auth.acceptTerms")}{" "}
              <Link to="/cgu" style={{ color: "var(--text-link)" }}>
                {t("auth.termsLink")}
              </Link>
            </span>
          </label>

          {error && <p className="text-xs" style={{ color: "var(--error-fg)" }}>{error}</p>}

          <Button type="submit" size="md" className="w-full" disabled={loading || !email.trim() || !password || !orgName.trim() || !acceptTerms}>
            {t("auth.signup")}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Link to="/login" className="text-xs font-medium" style={{ color: "var(--text-link)" }}>
            {t("auth.alreadyHaveAccount")}
          </Link>
        </div>
      </div>
    </div>
  );
}
