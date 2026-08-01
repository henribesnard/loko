import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Monitor, X } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PasswordStrength } from "@/components/ui/PasswordStrength";
import type { useAccountSettings } from "@/hooks/useAccountSettings";

interface Props {
  settings: ReturnType<typeof useAccountSettings>;
}

export function SecurityTab({ settings }: Props) {
  const { t } = useTranslation();
  const { sessions, changePassword, revokeSession, revokeOtherSessions } = settings;
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChangePassword = async () => {
    setPwError("");
    if (newPw !== confirmPw) {
      setPwError(t("account.security.passwordMismatch"));
      return;
    }
    setSaving(true);
    try {
      await changePassword(currentPw, newPw);
      setPwSuccess(true);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setTimeout(() => setPwSuccess(false), 3000);
    } catch (e: any) {
      setPwError(e.message || "Erreur");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Password change */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("account.security.changePassword")}
        </h2>
        <Input
          label={t("account.security.currentPassword")}
          type="password"
          value={currentPw}
          onChange={(e) => setCurrentPw(e.target.value)}
        />
        <div className="space-y-1">
          <Input
            label={t("account.security.newPassword")}
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
          />
          <PasswordStrength password={newPw} />
        </div>
        <Input
          label={t("account.security.confirmPassword")}
          type="password"
          value={confirmPw}
          onChange={(e) => setConfirmPw(e.target.value)}
        />
        {pwError && <p className="text-xs" style={{ color: "var(--error-fg)" }}>{pwError}</p>}
        {pwSuccess && (
          <p className="text-xs" style={{ color: "var(--success-fg)" }}>
            {t("account.security.passwordChanged")}
          </p>
        )}
        <Button onClick={handleChangePassword} disabled={saving || !currentPw || !newPw}>
          {t("account.security.updatePassword")}
        </Button>
      </section>

      {/* Active sessions */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("account.security.sessions")}
          </h2>
          {sessions.length > 1 && (
            <Button size="sm" variant="secondary" onClick={revokeOtherSessions}>
              {t("account.security.logoutAll")}
            </Button>
          )}
        </div>
        <div className="space-y-2">
          {sessions.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between px-4 py-3"
              style={{
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-subtle)",
                background: s.is_current ? "var(--brand-primary-tint)" : "var(--surface-card)",
              }}
            >
              <div className="flex items-center gap-3">
                <Monitor size={16} style={{ color: "var(--text-tertiary)" }} />
                <div>
                  <p className="text-sm" style={{ color: "var(--text-primary)" }}>
                    {s.user_agent ? s.user_agent.slice(0, 60) : "—"}
                    {s.is_current && (
                      <Badge label={t("account.security.currentSession")} variant="brand" className="ml-2" />
                    )}
                  </p>
                  <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                    {s.ip_address || "—"} · {new Date(s.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              {!s.is_current && (
                <button
                  onClick={() => revokeSession(s.id)}
                  className="p-1 hover:opacity-70"
                  aria-label={t("account.security.logoutSession")}
                >
                  <X size={14} style={{ color: "var(--text-tertiary)" }} />
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* 2FA placeholder */}
      <section
        className="p-4 space-y-2"
        style={{
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border-subtle)",
          background: "var(--surface-card)",
        }}
      >
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("account.security.twoFactor")}
          </h3>
          <Badge label={t("account.security.comingSoon")} variant="info" />
        </div>
        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          {t("account.security.twoFactorDesc")}
        </p>
      </section>
    </div>
  );
}
