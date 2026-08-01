import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { LokoLockup } from "@/components/ui/LokoLockup";

interface InviteInfo {
  email: string;
  role: string;
  org_name: string;
  expires_at: string;
}

export function InvitePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Accept form
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Token manquant.");
      setLoading(false);
      return;
    }
    api<InviteInfo>(`/api/invitations/${token}`)
      .then(setInfo)
      .catch(() => setError("Invitation introuvable ou expiree."))
      .finally(() => setLoading(false));
  }, [token]);

  const handleAccept = async () => {
    setAccepting(true);
    setError("");
    try {
      await api("/api/invitations/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          password: password || undefined,
          display_name: displayName || undefined,
        }),
      });
      navigate("/bot");
    } catch (e: any) {
      setError(e.message || "Erreur");
      setAccepting(false);
    }
  };

  const roleLabels: Record<string, string> = {
    owner: t("account.team.roles.owner"),
    editor: t("account.team.roles.editor"),
    viewer: t("account.team.roles.viewer"),
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-page">
        <p className="text-sm text-loko-tertiary">{t("common.loading")}</p>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-page">
        <div className="max-w-sm text-center space-y-4">
          <LokoLockup height={28} />
          <p className="text-sm" style={{ color: "var(--error-fg)" }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center bg-surface-page">
      <div
        className="w-full max-w-md p-8 space-y-6"
        style={{
          borderRadius: "var(--radius-lg)",
          background: "var(--surface-card)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <div className="text-center space-y-2">
          <LokoLockup height={28} />
          <h1 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("invite.joinTitle", { org: info.org_name })}
          </h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {t("invite.invitedAs")}{" "}
            <Badge label={roleLabels[info.role] || info.role} variant="brand" />
          </p>
        </div>

        <div className="space-y-4">
          <Input
            label={t("invite.name")}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={t("invite.namePlaceholder")}
          />
          <Input
            label={t("invite.password")}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("invite.passwordPlaceholder")}
          />
          {error && <p className="text-xs" style={{ color: "var(--error-fg)" }}>{error}</p>}
          <Button className="w-full" onClick={handleAccept} disabled={accepting || !password}>
            {t("invite.accept")}
          </Button>
        </div>
      </div>
    </div>
  );
}
